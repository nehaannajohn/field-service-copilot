from offline_pipeline.checks import completeness_problem, fill_english, transformation_problem
from offline_pipeline.inputs import ModelInput


def unit(text, unit_type="record", lang="en", text_en=None):
    return {"unit_type": unit_type, "lang": lang, "text_original": text, "text_en": text_en}


def csv_input(rows):
    return ModelInput(1, 1, {"type": "input_text", "text": "id;note\n" + "".join(f"{i};x\n" for i in range(rows))})


def test_record_count_mismatch_is_caught():
    servio_like = {"units": [unit("The supplied CSV ... exceeds the response-size limit")]}
    assert completeness_problem(".csv", csv_input(3), servio_like) == "expected at least 3 records, got 1"


def test_matching_record_count_passes():
    assert completeness_problem(".csv", csv_input(2), {"units": [unit("a"), unit("b")]}) is None


def test_translation_listed_without_text_en_is_caught():
    result = {"transformations_applied": ["translation"], "units": [unit("geen lek", lang="en")]}
    assert transformation_problem(result) == "translation listed but no unit has text_en"


def test_text_en_without_translation_listed_is_caught():
    result = {"transformations_applied": [], "units": [unit("geen lek", lang="nl", text_en="no leak")]}
    assert transformation_problem(result) == "units have text_en but translation is not listed"


def test_untranslated_non_english_unit_is_caught():
    result = {"transformations_applied": ["translation"],
              "units": [unit("geen lek", lang="nl", text_en="no leak"), unit("bijgevuld", lang="nl")]}
    assert transformation_problem(result) == "a non-English unit has no text_en"


def test_consistent_translation_passes():
    result = {"transformations_applied": ["translation"],
              "units": [unit("geen lek", lang="nl", text_en="no leak"), unit("ok", lang="en")]}
    assert transformation_problem(result) is None


def test_english_filled_from_original():
    result = {"units": [unit("already English")]}
    fill_english(result)
    assert result["units"][0]["text_en"] == "already English"


def test_messages_count_as_records_for_json_parts():
    json_input = ModelInput(1, 1, {"type": "input_text", "text": '[{"id": 1}, {"id": 2}, {"id": 3}]'})
    messages = {"units": [unit("hi", "message"), unit("re: hi", "message"), unit("ok", "message")]}
    assert completeness_problem(".json", json_input, messages) is None


def test_nested_messages_may_exceed_record_count():
    json_input = ModelInput(1, 1, {"type": "input_text", "text": '[{"id": 1}, {"id": 2}]'})
    case_with_comments = {"units": [unit("case 1"), unit("comment on case 1", "message"), unit("case 2")]}
    assert completeness_problem(".json", json_input, case_with_comments) is None
