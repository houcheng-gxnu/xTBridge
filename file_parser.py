"""文件解析：Gaussian .gjf / xTB .xyz / ORCA .allxyz 等格式的坐标解析与分子加载。"""

import math
import os
import re
from pathlib import Path

from .atom_data import ATOM_RADII


def _auto_bonds(atoms: list) -> list:
    """根据共价半径自动推断化学键。"""
    bonds = []
    for i, a in enumerate(atoms):
        for j in range(i + 1, len(atoms)):
            b = atoms[j]
            r1 = ATOM_RADII.get(a['sym'], 1.5)
            r2 = ATOM_RADII.get(b['sym'], 1.5)
            dx = a['x'] - b['x']
            dy = a['y'] - b['y']
            dz = a['z'] - b['z']
            if math.sqrt(dx*dx + dy*dy + dz*dz) < r1 + r2 + 0.45:
                bonds.append((a['idx'], b['idx']))
    return bonds


def parse_gjf_coords_all(path: str) -> list:
    """解析 .gjf，返回多组坐标 (支持 qst2/qst3)。
    每组为 [{'idx','sym','x','y','z'}, ...]。
    """
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = content.splitlines()

    # 检测路由段是否 qst2/qst3
    has_qst = False
    for line in lines:
        s = line.strip()
        if s.startswith("#") and ("qst2" in s.lower() or "qst3" in s.lower()):
            has_qst = True
            break

    all_sets = []
    found_blank = 0
    past_first_charge_mult = False
    current_atoms = []
    idx = 0

    for line in lines:
        s = line.strip()
        if not s:
            found_blank += 1
            if found_blank >= 2 and not past_first_charge_mult:
                past_first_charge_mult = True
            if past_first_charge_mult and current_atoms:
                all_sets.append(current_atoms)
                current_atoms = []
                idx = 0
            continue
        if past_first_charge_mult:
            parts = s.split()
            if len(parts) >= 4:
                sym = parts[0].capitalize()
                try:
                    float(parts[1])
                    if sym[0].isalpha() and sym.isalpha():
                        idx += 1
                        current_atoms.append({
                            'idx': idx, 'sym': sym,
                            'x': float(parts[1]), 'y': float(parts[2]), 'z': float(parts[3]),
                        })
                    else:
                        pass
                except (ValueError, IndexError):
                    if current_atoms:
                        all_sets.append(current_atoms)
                        current_atoms = []
                        idx = 0
    if current_atoms:
        all_sets.append(current_atoms)

    all_sets = [s for s in all_sets if len(s) >= 3]

    if not has_qst:
        return all_sets[:1]
    return all_sets[:2]


def parse_gjf_coords(path: str) -> list:
    """解析 .gjf 第一组坐标（保持向后兼容）。"""
    sets = parse_gjf_coords_all(path)
    return sets[0] if sets else []


def parse_xyz_coords(path: str) -> list:
    """解析 .xyz 文件。"""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except Exception:
        return []
    if len(lines) < 3:
        return []
    try:
        natoms = int(lines[0].strip())
    except ValueError:
        return []
    atoms = []
    for i, line in enumerate(lines[2:2 + natoms]):
        parts = line.split()
        if len(parts) >= 4:
            try:
                atoms.append({
                    'idx': i + 1, 'sym': parts[0].capitalize(),
                    'x': float(parts[1]), 'y': float(parts[2]), 'z': float(parts[3]),
                })
            except (ValueError, IndexError):
                continue
    return atoms


def parse_xtb_scan_log(path: str) -> list:
    """解析 xtbscan.log，返回 [{step, energy, energy_relative, atoms}, ...]。
    相对能量以 kcal/mol 计，零点为最低能量构型。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = text.strip().splitlines()
    results = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        try:
            natoms = int(line)
        except (ValueError, IndexError):
            i += 1
            continue
        i += 1
        if i >= len(lines):
            break
        m = re.search(r'energy:\s*([-\d.]+)', lines[i].strip())
        if not m:
            i += 1
            continue
        energy = float(m.group(1))
        i += 1
        atoms = []
        for j in range(natoms):
            if i + j >= len(lines):
                break
            parts = lines[i + j].split()
            if len(parts) >= 4:
                try:
                    atoms.append({
                        'idx': j + 1,
                        'sym': parts[0].capitalize(),
                        'x': float(parts[1]), 'y': float(parts[2]), 'z': float(parts[3]),
                    })
                except (ValueError, IndexError):
                    continue
        i += natoms
        if atoms:
            results.append({'step': len(results) + 1, 'energy': energy, 'atoms': atoms})
    if results:
        e_min = min(r['energy'] for r in results)
        for r in results:
            r['energy_relative'] = (r['energy'] - e_min) * 627.509469
    return results


def load_molecule(path: str) -> tuple:
    """加载分子文件，返回 (list_of_atoms_list, list_of_bonds_list)。
    普通 gjf → ([atoms], [bonds])
    qst2 gjf → ([atoms1, atoms2], [bonds1, bonds2])
    """
    ext = Path(path).suffix.lower()
    if ext in ('.gjf', '.com'):
        atom_sets = parse_gjf_coords_all(path)
    elif ext == '.xyz':
        atom_sets = [parse_xyz_coords(path)]
    else:
        atom_sets = [parse_xyz_coords(path)]
        if not atom_sets[0]:
            atom_sets = parse_gjf_coords_all(path)
    bond_sets = [_auto_bonds(a) for a in atom_sets]
    return atom_sets, bond_sets


def parse_last_standard_orientation(out_path: str) -> list:
    """从 Gaussian .out 文件中提取最后一个 Standard orientation 的坐标。
    只读取文件末尾 2MB，避免大文件全量加载。"""
    MAX_TAIL = 2 * 1024 * 1024  # 2 MB
    try:
        fsize = os.path.getsize(out_path)
        with open(out_path, "r", encoding="utf-8", errors="replace") as f:
            if fsize > MAX_TAIL:
                f.seek(fsize - MAX_TAIL)
                f.readline()
            content = f.read()
    except Exception:
        return []
    lines = content.splitlines()
    last_start = None
    for i in range(len(lines) - 1, -1, -1):
        if "Standard orientation:" in lines[i]:
            last_start = i
            break
    if last_start is None:
        return []
    atoms = []
    atomic_number_map = {
        "1": "H", "2": "He", "3": "Li", "4": "Be", "5": "B",
        "6": "C", "7": "N", "8": "O", "9": "F", "10": "Ne",
        "11": "Na", "12": "Mg", "13": "Al", "14": "Si", "15": "P",
        "16": "S", "17": "Cl", "18": "Ar", "19": "K", "20": "Ca",
        "21": "Sc", "22": "Ti", "23": "V", "24": "Cr", "25": "Mn",
        "26": "Fe", "27": "Co", "28": "Ni", "29": "Cu", "30": "Zn",
        "31": "Ga", "32": "Ge", "33": "As", "34": "Se", "35": "Br",
        "36": "Kr", "37": "Rb", "38": "Sr", "39": "Y", "40": "Zr",
        "41": "Nb", "42": "Mo", "43": "Tc", "44": "Ru", "45": "Rh",
        "46": "Pd", "47": "Ag", "48": "Cd", "49": "In", "50": "Sn",
        "51": "Sb", "52": "Te", "53": "I", "54": "Xe", "55": "Cs",
        "56": "Ba", "57": "La", "72": "Hf", "73": "Ta", "74": "W",
        "75": "Re", "76": "Os", "77": "Ir", "78": "Pt", "79": "Au",
        "80": "Hg", "81": "Tl", "82": "Pb", "83": "Bi",
    }
    sep_count = 0
    for i in range(last_start, len(lines)):
        s = lines[i].strip()
        if "-----" in s:
            sep_count += 1
            if sep_count == 3:
                break
            continue
        if sep_count == 2 and s:
            parts = s.split()
            if len(parts) >= 6:
                try:
                    atomic_num = str(int(parts[1]))
                    sym = atomic_number_map.get(atomic_num, parts[1])
                    atoms.append({
                        'idx': int(parts[0]),
                        'sym': sym,
                        'x': float(parts[3]),
                        'y': float(parts[4]),
                        'z': float(parts[5]),
                    })
                except (ValueError, IndexError):
                    continue
    return atoms


def parse_orca_allxyz(path: str) -> list:
    """解析 ORCA 扫描 .allxyz 文件，返回 [{step, energy, atoms}, ...]。
    相对能量以 kcal/mol 计。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    blocks = re.split(r'\n\s*>\s*\n', text.strip())
    results = []
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        header = ""
        header_idx = 0
        natoms = 0
        for j, ln in enumerate(lines):
            if "Step" in ln and "E" in ln and "Coordinates" in ln:
                header = ln
                header_idx = j
                try:
                    natoms = int(lines[j - 1].strip())
                except Exception:
                    natoms = 0
                break
        if not header or natoms == 0:
            continue
        m_step = re.search(r'Step\s+(\d+)', header)
        m_e = re.search(r'E\s+([-\d.]+)', header)
        if not m_step or not m_e:
            continue
        step_num = int(m_step.group(1))
        energy_val = float(m_e.group(1))
        atoms = []
        coord_start = header_idx + 1
        for k in range(coord_start, min(coord_start + natoms, len(lines))):
            parts = lines[k].split()
            if len(parts) >= 4:
                try:
                    atoms.append({
                        'idx': k - coord_start + 1,
                        'sym': parts[0].capitalize(),
                        'x': float(parts[1]), 'y': float(parts[2]),
                        'z': float(parts[3]),
                    })
                except (ValueError, IndexError):
                    continue
        if atoms:
            results.append({
                'step': step_num,
                'energy': energy_val,
                'atoms': atoms,
            })
    if not results:
        return []
    min_e = min(r['energy'] for r in results)
    for r in results:
        r['energy_relative'] = (r['energy'] - min_e) * 627.5095
    return sorted(results, key=lambda r: r['step'])
