from online_query.retrieve import Retrieved
from online_query.verify import derive_results


def chunk(cid, text):
    return Retrieved(cid, "corpus/x.pdf", "X", "manual", "unknown", "unknown", {}, cid, text, text, "",
                     None, None, None, 0.0)


IOM = chunk("iom", "Casing bolt tightening torque 45 N-m, cross pattern, two passes")
SB = chunk("sb", "From serial HCP350-240001 the casing bolt torque is 38 N-m")
CLAIM = {"id": "c1", "text": "For serials from HCP350-240001 the torque is 38 N-m", "citations": ["sb"]}


def cell(chunk_id, verdict, evidence):
    return {"claim_id": "c1", "chunk_id": chunk_id, "verdict": verdict, "evidence": evidence}


def test_supported_by_own_citation():
    r = derive_results([CLAIM], [SB], [cell("sb", "supports", "the casing bolt torque is 38 N-m")], {"sb"})
    assert r["c1"]["status"] == "supported" and r["c1"]["kept"]


def test_sources_disagree_is_kept_with_both_sides():
    cells = [cell("sb", "supports", "the casing bolt torque is 38 N-m"),
             cell("iom", "contradicts", "Casing bolt tightening torque 45 N-m")]
    r = derive_results([CLAIM], [SB, IOM], cells, {"sb", "iom"})
    assert r["c1"]["status"] == "sources_disagree" and r["c1"]["contradicting"] == ["iom"] and r["c1"]["kept"]


def test_contradicted_without_support_is_dropped():
    r = derive_results([CLAIM], [IOM], [cell("iom", "contradicts", "Casing bolt tightening torque 45 N-m")], {"iom"})
    assert r["c1"]["status"] == "contradicted" and not r["c1"]["kept"]


def test_support_from_uncited_chunk_corrects_citation():
    claim = {**CLAIM, "citations": ["iom"]}
    cells = [cell("sb", "supports", "the casing bolt torque is 38 N-m"), cell("iom", "irrelevant", None)]
    r = derive_results([claim], [SB, IOM], cells, {"sb", "iom"})
    assert r["c1"]["status"] == "supported_citation_corrected" and r["c1"]["citations"] == ["sb"]


def test_citation_outside_retrieved_set_fails():
    r = derive_results([{**CLAIM, "citations": ["sb", "secret"]}], [SB],
                       [cell("sb", "supports", "the casing bolt torque is 38 N-m")], {"sb"})
    assert r["c1"]["status"] == "unsupported"
    assert "citation not permitted: secret" in r["c1"]["failed_checks"]
