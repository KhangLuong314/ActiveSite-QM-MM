"""Ligand hydrogen placement with RDKit. Runs INSIDE the activesite-prep:at26 container.

argv: ligand.pdb SMILES protonate_atom|- out.sdf

Loads the crystal ligand without hydrogens, assigns bond orders from the SMILES
template, optionally protonates one named nitrogen (+1 formal charge, one
explicit H), adds hydrogens with coordinates, writes the SDF and prints one
JSON line: {heavy_atoms, protonated, atoms_with_h, net_charge, smiles}.

This file must stay free of activesite imports: it is copied into the work
directory and executed by the container's "prep" environment.
"""
import json
import sys


def main(argv):
    if len(argv) != 5:
        sys.stderr.write("usage: ligand_rdkit.py ligand.pdb SMILES protonate_atom|- out.sdf\n")
        return 2
    pdb_path, smiles, protonate_atom, out_sdf = argv[1:]
    from rdkit import Chem
    from rdkit.Chem import AllChem

    with open(pdb_path, "r", encoding="utf-8") as f:
        block = f.read()
    mol = Chem.MolFromPDBBlock(block, removeHs=True, sanitize=False)
    if mol is None:
        raise SystemExit("RDKit could not read the ligand PDB")
    template = Chem.MolFromSmiles(smiles)
    if template is None:
        raise SystemExit("RDKit could not parse the SMILES template")
    mol = AllChem.AssignBondOrdersFromTemplate(template, mol)

    protonated = None
    if protonate_atom and protonate_atom != "-":
        target = None
        for atom in mol.GetAtoms():
            info = atom.GetPDBResidueInfo()
            if info is not None and info.GetName().strip() == protonate_atom:
                target = atom
                break
        if target is None:
            raise SystemExit(f"atom {protonate_atom} not found in ligand PDB")
        if target.GetSymbol() != "N":
            raise SystemExit(f"atom {protonate_atom} is {target.GetSymbol()}, not N")
        target.SetFormalCharge(1)
        target.SetNumExplicitHs(1)
        target.SetNoImplicit(True)
        protonated = protonate_atom
    Chem.SanitizeMol(mol)

    heavy = mol.GetNumAtoms()
    mol_h = Chem.AddHs(mol, addCoords=True)
    net_charge = sum(a.GetFormalCharge() for a in mol_h.GetAtoms())
    mol_h.SetProp("_Name", "LIG")
    writer = Chem.SDWriter(out_sdf)
    writer.write(mol_h)
    writer.close()
    print(json.dumps({
        "heavy_atoms": heavy,
        "protonated": protonated,
        "atoms_with_h": mol_h.GetNumAtoms(),
        "net_charge": int(net_charge),
        "smiles": Chem.MolToSmiles(Chem.RemoveHs(mol_h)),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
