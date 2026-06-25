"""原子数据：共价半径、原子序数、颜色表、多重度文本、溶剂列表。"""

ATOM_RADII = {
    'H': 0.50, 'He': 0.28, 'Li': 1.28, 'Be': 0.96, 'B': 0.84,
    'C': 0.76, 'N': 0.71, 'O': 0.66, 'F': 0.57, 'Ne': 0.58,
    'Na': 1.66, 'Mg': 1.41, 'Al': 1.21, 'Si': 1.11, 'P': 1.07,
    'S': 1.05, 'Cl': 1.02, 'Ar': 1.06, 'K': 2.03, 'Ca': 1.76,
    'Sc': 1.7, 'Ti': 1.6, 'V': 1.53, 'Cr': 1.39, 'Mn': 1.39,
    'Fe': 1.32, 'Co': 1.26, 'Ni': 1.24, 'Cu': 1.32, 'Zn': 1.22,
    'Ga': 1.22, 'Ge': 1.2, 'As': 1.19, 'Se': 1.2, 'Br': 1.2,
    'Kr': 1.16, 'Rb': 2.2, 'Sr': 1.95, 'Y': 1.9, 'Zr': 1.75,
    'Nb': 1.64, 'Mo': 1.54, 'Tc': 1.47, 'Ru': 1.46, 'Rh': 1.42,
    'Pd': 1.39, 'Ag': 1.45, 'Cd': 1.44, 'In': 1.42, 'Sn': 1.39,
    'Sb': 1.39, 'Te': 1.38, 'I': 1.39, 'Xe': 1.4, 'Cs': 2.44,
    'Ba': 2.15, 'La': 2.07, 'Ce': 2.04, 'Pr': 2.03, 'Nd': 2.01,
    'Pm': 1.99, 'Sm': 1.98, 'Eu': 1.98, 'Gd': 1.96, 'Tb': 1.94,
    'Dy': 1.92, 'Ho': 1.92, 'Er': 1.89, 'Tm': 1.9, 'Yb': 1.87,
    'Lu': 1.87, 'Hf': 1.75, 'Ta': 1.7, 'W': 1.62, 'Re': 1.51,
    'Os': 1.44, 'Ir': 1.41, 'Pt': 1.36, 'Au': 1.36, 'Hg': 1.32,
    'Tl': 1.45, 'Pb': 1.46, 'Bi': 1.48, 'Po': 1.4, 'At': 1.5,
    'Rn': 1.5, 'Fr': 2.6, 'Ra': 2.21, 'Ac': 2.15, 'Th': 2.06,
    'Pa': 2.0, 'U': 1.96, 'Np': 1.9, 'Pu': 1.87, 'Am': 1.8,
    'Cm': 1.69,
}

ATOMIC_NUMBERS = {
    'H': 1, 'He': 2, 'Li': 3, 'Be': 4, 'B': 5, 'C': 6, 'N': 7, 'O': 8, 'F': 9, 'Ne': 10,
    'Na': 11, 'Mg': 12, 'Al': 13, 'Si': 14, 'P': 15, 'S': 16, 'Cl': 17, 'Ar': 18,
    'K': 19, 'Ca': 20, 'Sc': 21, 'Ti': 22, 'V': 23, 'Cr': 24, 'Mn': 25, 'Fe': 26,
    'Co': 27, 'Ni': 28, 'Cu': 29, 'Zn': 30, 'Ga': 31, 'Ge': 32, 'As': 33, 'Se': 34,
    'Br': 35, 'Kr': 36, 'Rb': 37, 'Sr': 38, 'Y': 39, 'Zr': 40, 'Nb': 41, 'Mo': 42,
    'Tc': 43, 'Ru': 44, 'Rh': 45, 'Pd': 46, 'Ag': 47, 'Cd': 48, 'In': 49, 'Sn': 50,
    'Sb': 51, 'Te': 52, 'I': 53, 'Xe': 54, 'Cs': 55, 'Ba': 56, 'La': 57, 'Hf': 72,
    'Ta': 73, 'W': 74, 'Re': 75, 'Os': 76, 'Ir': 77, 'Pt': 78, 'Au': 79, 'Hg': 80,
    'Tl': 81, 'Pb': 82, 'Bi': 83,
}

_MULT_TEXT = {1: "singlet", 2: "doublet", 3: "triplet", 4: "quartet",
              5: "quintet", 6: "sextet", 7: "septet", 8: "octet"}

ATOM_COLORS = {
    'H': '#CCCCCC', 'C': '#8E8E8E', 'N': '#1818E4', 'O': '#E40000',
    'F': '#B1FFFF', 'S': '#FFC628', 'P': '#FF7E00', 'Cl': '#18EF18',
    'Br': '#A52020', 'I': '#930093', 'Si': '#7E9999', 'B': '#FFB4B4',
    'Fe': '#7E79C6', 'Co': '#5B6DFF', 'Ni': '#5B79C1', 'Cu': '#FF7960',
    'Zn': '#7C7EAF', 'Ru': '#238E95', 'Rh': '#097C8B', 'Pd': '#006783',
    'Ag': '#99C6FF', 'Pt': '#165B8E', 'Au': '#FFD023', 'Hg': '#B4B4C1',
    'He': '#D8FFFF', 'Li': '#CC7CFF', 'Be': '#CCFF00',
    'Ne': '#AFE2F4', 'Na': '#AA5BF1', 'Mg': '#B1CC00',
    'Al': '#D0A5A5', 'Ar': '#7ED0E2', 'K': '#8E3FD3', 'Ca': '#999900',
    'Sc': '#E4E4E2', 'Ti': '#BEC1C6', 'V': '#A5A5AA', 'Cr': '#8999C6',
    'Mn': '#9A79C6', 'Ga': '#C18E8E', 'Ge': '#668E8E',
    'As': '#BC7EE2', 'Se': '#FFA000', 'Kr': '#5BB9D0',
    'Rb': '#6F2DAF', 'Sr': '#7E6600', 'Y': '#93FBFF', 'Zr': '#93DFDF',
    'Nb': '#72C1C8', 'Mo': '#53B4B4', 'Tc': '#3A9DA7',
}

ALPB_SOLVENTS = [
    "acetone", "acetonitrile", "aniline", "benzaldehyde", "benzene",
    "ch2cl2", "chcl3", "cs2", "dioxane", "dmf", "dmso", "ether",
    "ethylacetate", "furane", "hexane", "methanol", "nitromethane",
    "octanol", "woctanol", "phenol", "thf", "toluene", "water",
]

COSMO_SOLVENTS = [
    "acetone", "acetonitrile", "benzene", "ch2cl2", "chcl3",
    "cs2", "dmf", "dmso", "ether", "ethylacetate", "furane",
    "hexane", "methanol", "nitromethane", "octanol", "woctanol",
    "phenol", "thf", "toluene", "water",
]
