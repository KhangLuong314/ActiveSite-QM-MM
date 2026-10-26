"""Unit tests for ProtonationAgent and Track 02 protonation Decision Cards."""
from activesite.chem.protonation import ProtonationAgent


def test_his_metal_coordination_hie():
    agent = ProtonationAgent(default_ph=7.4)
    # His119 coordinating Mg2+ in I-PpoI
    res = agent.evaluate_residue(
        resname="HIS",
        resid=119,
        chain="A",
        coordinating_metal="Mg2+",
    )
    assert res.state == "HIE"
    assert res.formal_charge == 0
    assert res.decision_card is not None
    assert "Mg2+" in res.decision_card.rationale
    assert any("HIP" in alt.name for alt in res.decision_card.alternatives)


def test_asp_buried_neutral():
    agent = ProtonationAgent(default_ph=7.4)
    res = agent.evaluate_residue(
        resname="ASP",
        resid=381,
        buried_hydrophobic=True,
    )
    # Elevated pKa shifts Asp to ASH at neutral pH
    assert res.state == "ASH"
    assert res.formal_charge == 0
    assert "desolvation" in res.decision_card.rationale.lower()


def test_erlotinib_aq4_protonation():
    agent = ProtonationAgent(default_ph=7.4)
    charge, card = agent.evaluate_ligand("AQ4")
    assert charge == 0
    assert "quinazoline" in card.rationale.lower()
    assert card.confidence >= 0.90


def test_imatinib_sti_protonation():
    agent = ProtonationAgent(default_ph=7.4)
    charge, card = agent.evaluate_ligand("STI")
    assert charge == 1
    assert "piperazin" in card.rationale.lower()
    assert len(card.alternatives) >= 1
