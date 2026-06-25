"""Tests for enhanced StructuredMetric fields: period_granularity, yoy_data, qoq_data."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from app.schemas.agent import StructuredMetric, MetricDataPoint


class TestMetricDataPoint:
    def test_basic(self):
        dp = MetricDataPoint(label="2020", value=100.0)
        assert dp.label == "2020"
        assert dp.value == 100.0

    def test_defaults_removed(self):
        dp = MetricDataPoint(label="Q1", value=50.5)
        assert dp.label == "Q1"
        assert dp.value == 50.5


class TestStructuredMetricPeriodGranularity:
    def test_default_is_empty(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
        )
        assert m.period_granularity == ""

    def test_year_granularity(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
            period_granularity="year",
        )
        assert m.period_granularity == "year"

    def test_quarter_granularity(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
            period_granularity="quarter",
        )
        assert m.period_granularity == "quarter"

    def test_month_granularity(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
            period_granularity="month",
        )
        assert m.period_granularity == "month"

    def test_week_granularity(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
            period_granularity="week",
        )
        assert m.period_granularity == "week"


class TestStructuredMetricYoYData:
    def test_default_is_none(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
        )
        assert m.yoy_data is None

    def test_with_yoy_data(self):
        yoy = [MetricDataPoint(label="2021", value=12.5), MetricDataPoint(label="2022", value=15.0)]
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
            yoy_data=yoy,
        )
        assert m.yoy_data is not None
        assert len(m.yoy_data) == 2
        assert m.yoy_data[0].label == "2021"
        assert m.yoy_data[0].value == 12.5
        assert m.yoy_data[1].label == "2022"
        assert m.yoy_data[1].value == 15.0


class TestStructuredMetricQoQData:
    def test_default_is_none(self):
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
        )
        assert m.qoq_data is None

    def test_with_qoq_data(self):
        qoq = [MetricDataPoint(label="Q1", value=5.0), MetricDataPoint(label="Q2", value=8.0)]
        m = StructuredMetric(
            metric_name="test",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
            qoq_data=qoq,
        )
        assert m.qoq_data is not None
        assert len(m.qoq_data) == 2
        assert m.qoq_data[0].label == "Q1"
        assert m.qoq_data[0].value == 5.0


class TestStructuredMetricFullObject:
    def test_full_metric_with_all_new_fields(self):
        data = [MetricDataPoint(label="2020", value=100), MetricDataPoint(label="2021", value=120)]
        yoy = [MetricDataPoint(label="2021", value=20.0)]
        qoq = [MetricDataPoint(label="Q1", value=3.5), MetricDataPoint(label="Q2", value=4.2)]
        m = StructuredMetric(
            metric_name="Global AI Chip Market",
            metric_type="yearly_trend",
            unit="billion USD",
            dimension="industry",
            data_points=data,
            period_granularity="year",
            yoy_data=yoy,
            qoq_data=qoq,
            source="Industry Report 2024",
            chart_type_hint="line",
        )
        assert m.metric_name == "Global AI Chip Market"
        assert m.period_granularity == "year"
        assert m.yoy_data is not None
        assert len(m.yoy_data) == 1
        assert m.qoq_data is not None
        assert len(m.qoq_data) == 2
        assert m.chart_type_hint == "line"

    def test_backward_compat_no_new_fields(self):
        m = StructuredMetric(
            metric_name="legacy metric",
            data_points=[MetricDataPoint(label="a", value=1), MetricDataPoint(label="b", value=2)],
        )
        assert m.period_granularity == ""
        assert m.yoy_data is None
        assert m.qoq_data is None
        assert m.metric_type == "other"
        assert m.chart_type_hint == "bar"


class TestParseStructuredMetrics:
    """Test AnalyzerAgent._parse_structured_metrics with new fields."""

    def _get_parser(self):
        from app.agents.analyzer import AnalyzerAgent
        agent = AnalyzerAgent.__new__(AnalyzerAgent)
        return agent._parse_structured_metrics

    def test_parse_with_period_granularity(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Market Size",
                "metric_type": "yearly_trend",
                "unit": "billion",
                "dimension": "trend",
                "data_points": [{"label": "2020", "value": 100}, {"label": "2021", "value": 120}],
                "period_granularity": "year",
                "source": "Report",
                "chart_type_hint": "line",
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        assert result[0].period_granularity == "year"

    def test_parse_with_yoy_data(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Revenue",
                "metric_type": "yearly_trend",
                "data_points": [{"label": "2020", "value": 100}, {"label": "2021", "value": 120}],
                "period_granularity": "year",
                "yoy_data": [{"label": "2020", "value": 10.0}, {"label": "2021", "value": 20.0}],
                "chart_type_hint": "line",
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        assert result[0].yoy_data is not None
        assert len(result[0].yoy_data) == 2

    def test_parse_with_qoq_data(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Quarterly Revenue",
                "metric_type": "quarterly_trend",
                "data_points": [{"label": "Q1", "value": 50}, {"label": "Q2", "value": 60}],
                "period_granularity": "quarter",
                "qoq_data": [{"label": "Q1", "value": 5.0}, {"label": "Q2", "value": 10.0}],
                "chart_type_hint": "line",
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        assert result[0].qoq_data is not None
        assert len(result[0].qoq_data) == 2

    def test_parse_invalid_granularity_falls_back(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Test",
                "data_points": [{"label": "a", "value": 1}, {"label": "b", "value": 2}],
                "period_granularity": "invalid_value",
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        assert result[0].period_granularity == ""

    def test_parse_yoy_with_insufficient_points_becomes_none(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Test",
                "data_points": [{"label": "a", "value": 1}, {"label": "b", "value": 2}],
                "yoy_data": [{"label": "only_one", "value": 5.0}],
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        assert result[0].yoy_data is None

    def test_parse_all_fields_combined(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Global AI Chip Market",
                "metric_type": "yearly_trend",
                "unit": "billion USD",
                "dimension": "industry",
                "data_points": [
                    {"label": "2020", "value": 100},
                    {"label": "2021", "value": 130},
                ],
                "period_granularity": "year",
                "yoy_data": [
                    {"label": "2020", "value": 10.0},
                    {"label": "2021", "value": 30.0},
                ],
                "qoq_data": [
                    {"label": "Q1", "value": 5.0},
                    {"label": "Q2", "value": 8.0},
                ],
                "source": "Industry Report",
                "chart_type_hint": "line",
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        m = result[0]
        assert m.metric_name == "Global AI Chip Market"
        assert m.period_granularity == "year"
        assert m.yoy_data is not None
        assert len(m.yoy_data) == 2
        assert m.qoq_data is not None
        assert len(m.qoq_data) == 2
        assert m.chart_type_hint == "line"

    def test_parse_backward_compat_old_format(self):
        parse = self._get_parser()
        raw = [
            {
                "metric_name": "Legacy Metric",
                "metric_type": "market_share",
                "unit": "%",
                "data_points": [
                    {"label": "Company A", "value": 35},
                    {"label": "Company B", "value": 25},
                ],
                "source": "Old report",
            }
        ]
        result = parse(raw)
        assert len(result) == 1
        assert result[0].period_granularity == ""
        assert result[0].yoy_data is None
        assert result[0].qoq_data is None
        assert result[0].chart_type_hint == "bar"
