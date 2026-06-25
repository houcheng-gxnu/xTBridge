"""ORCA 工具：ORCA_EXE 路径、build_orca_input 输入文件生成。"""

import re
from datetime import datetime

ORCA_EXE = r"E:\ORCA\orca.exe"


def build_orca_input(atoms, charge, mult, method, basis, job_type,
                     solvent, solvent_name, nprocs, memory,
                     extra_keywords="", product_file=None, nimages=12,
                     neb_free_end=False, scan_block=""):
    """Build ORCA .inp file content from settings. Returns (inp_content, xyz_content)."""
    lines = []
    method_line = f"! {method}"
    if basis and method not in ("XTB2", "GFN2-xTB", "GFN1-xTB", "GFN0-xTB", "GFN-FF"):
        method_line += f" {basis}"
    if job_type and job_type != "SP" and job_type != "Scan":
        method_line += f" {job_type}"
    if job_type == "Scan":
        method_line += " Opt"
    lines.append(method_line)
    lines.append("")
    if nprocs > 1:
        lines.append(f"%pal nprocs {nprocs} end")
        lines.append("")
    if memory > 1024:
        lines.append(f"%maxcore {memory}")
        lines.append("")
    if solvent and solvent_name:
        lines.append(f'%cpcm smd true smdsolvent "{solvent_name}" end')
        lines.append("")
    if "NEB" in job_type and product_file:
        lines.append("%neb")
        lines.append(f' Product "{product_file}"')
        lines.append(f" NImages {nimages}")
        if neb_free_end:
            lines.append(" Free_End true")
        lines.append("end")
        lines.append("")
    if "Scan" in job_type and scan_block.strip():
        lines.append(scan_block.strip())
        lines.append("")
    if extra_keywords:
        lines.append(extra_keywords)
        lines.append("")
    xyz_lines = [f"{len(atoms)}", f"ORCA job {datetime.now():%Y-%m-%d %H:%M}"]
    for a in atoms:
        xyz_lines.append(f"{a['sym']:<2s}  {a['x']:15.8f}  {a['y']:15.8f}  {a['z']:15.8f}")
    return "\n".join(lines), "\n".join(xyz_lines)
