"""Offline presentation regressions; these are not new physical/AI trial results."""
import copy
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from triplens.analysis_contract import ANALYSIS_SCHEMA, normalize_claim, normalize_analysis

LONG = ('47.6초와 48.72초 사이에 LP 드럼 인벤토리 외란 지령 신호가 0.0에서 -160.0으로 감소하고, '
        '인벤토리 외란 유량이 0.0 t/h에서 -576.0 t/h로 급감하여 LP 드럼 수위 저하를 유발한 '
        '기동 원인으로 분석됩니다. 정확한 발생 시각은 미확인이며 표본 구간만 확인됩니다.')
SHORT = 'LP 드럼 재고량 감소 외란이 수위 저하의 원인 후보입니다.'

def claim(**changes):
    value = dict(claim=LONG, report_summary=SHORT, status='CANDIDATE',
                 evidence_ids=['RAW:21:vppLPDrumInventoryDisturbanceMassFlowTH',
                               'RAW:22:vppLPDrumInventoryDisturbanceMassFlowTH'],
                 related_tags=['vppLPDrumInventoryDisturbanceMassFlowTH'],
                 model_time_s=None, time_interval_s=[47.6, 48.72], ai_confidence=.84)
    return {**value, **changes}

class ConciseReportTests(unittest.TestCase):
    def presentation(self):
        self.assertIsNotNone(importlib.util.find_spec('triplens.report_presentation'),
                             'shared presentation validation must exist')
        return importlib.import_module('triplens.report_presentation')

    def test_both_provider_schema_separates_summary_from_detailed_claim(self):
        props = ANALYSIS_SCHEMA['properties']['primary_cause']['properties']
        self.assertIn('report_summary', props)
        self.assertIn('claim', props)
        self.assertIn('report_summary', ANALYSIS_SCHEMA['properties']['primary_cause']['required'])

    def test_summary_survives_normalization_without_changing_evidence_or_detail(self):
        source = claim(); before = copy.deepcopy(source)
        result = normalize_claim(source, 'primary_cause')
        self.assertEqual(result.get('report_summary'), SHORT)
        self.assertEqual(source, before)
        for key in ('claim', 'evidence_ids', 'related_tags', 'status', 'model_time_s', 'time_interval_s', 'ai_confidence'):
            self.assertEqual(result[key], source[key], key)

    def test_long_summary_is_rejected_not_truncated_or_used_as_diagnosis(self):
        source = claim(report_summary=LONG)
        result = normalize_claim(source, 'primary_cause')
        self.assertIsNone(result.get('report_summary'))
        self.assertTrue(result.get('report_summary_notes'))
        self.assertEqual(result['claim'], LONG)
        self.assertEqual(result['status'], 'CANDIDATE')
        self.assertEqual(result['time_interval_s'], [47.6, 48.72])

    def test_summary_cannot_introduce_numbers_tags_confirmation_or_hide_conflict(self):
        examples = [claim(report_summary='LP 드럼 외란 유량 999 t/h가 원인입니다.'),
                    claim(report_summary='vppInvented 신호가 원인 후보입니다.'),
                    claim(report_summary='LP 드럼 유출 외란이 원인으로 확정되었습니다.'),
                    claim(claim='HP BFP 푸시버튼은 원인 후보이나 RAW 불일치와 17.44초 지연은 추가 검증이 필요합니다.',
                          report_summary='HP BFP 푸시버튼 입력이 원인 후보입니다.')]
        for source in examples:
            with self.subTest(summary=source['report_summary']):
                result = normalize_claim(source, 'primary_cause')
                self.assertIsNone(result.get('report_summary'))
                self.assertTrue(result.get('report_summary_notes'))
                self.assertEqual(result['claim'], source['claim'])

    def test_confidence_changes_do_not_change_presentation_or_cause(self):
        a = normalize_claim(claim(ai_confidence=.3), 'primary_cause')
        b = normalize_claim(claim(ai_confidence=.95), 'primary_cause')
        self.assertEqual(a.get('report_summary'), SHORT)
        for key in ('claim', 'report_summary', 'status', 'evidence_ids', 'time_interval_s'):
            self.assertEqual(a[key], b[key])

    def test_legacy_short_claim_needs_no_extra_provider_request(self):
        p = self.presentation()
        self.assertEqual(p.summary_feedback({'primary_cause': {'claim': '원인 미확인', 'status': 'UNKNOWN'}}), [])

    def test_repair_only_updates_summary_and_rejects_other_fields(self):
        p = self.presentation()
        source = {'primary_cause': claim(report_summary=LONG), 'counter_evidence': [claim(report_summary=SHORT)]}
        before = copy.deepcopy(source)
        repaired = p.apply_summary_repair(source, {'summaries': [{'path': 'primary_cause', 'report_summary': SHORT}]})
        self.assertEqual(source, before)
        self.assertEqual(repaired['primary_cause']['report_summary'], SHORT)
        repaired['primary_cause']['report_summary'] = LONG
        self.assertEqual(repaired, before)
        with self.assertRaises(ValueError):
            p.apply_summary_repair(source, {'summaries': [{'path': 'primary_cause', 'report_summary': SHORT,
                                                          'status': 'CONFIRMED', 'model_time_s': 48.72}]})
        with self.assertRaises(ValueError):
            p.apply_summary_repair(source, {'summaries': [{'path': 'missing', 'report_summary': SHORT}]})

    def test_late_chronology_downgrade_revalidates_summary(self):
        raw = {'primary_cause': claim(model_time_s=90.0, time_interval_s=None),
               'direct_trigger': claim(claim='GT 트립', report_summary='GT 트립', model_time_s=85.633, time_interval_s=None)}
        result = normalize_analysis(raw)
        self.assertEqual(result['primary_cause']['status'], 'UNKNOWN')
        self.assertIsNone(result['primary_cause']['report_summary'])
        self.assertEqual(result['primary_cause']['claim'], LONG)

    def test_new_number_cannot_match_a_substring_of_a_source_number(self):
        source = claim(claim='외란 유량 900 t/h 증가가 원인 후보입니다.', report_summary='외란 유량 9 t/h가 원인 후보입니다.')
        self.assertIsNone(self.presentation().validate_summary(source)[0])

if __name__ == '__main__':
    unittest.main()
