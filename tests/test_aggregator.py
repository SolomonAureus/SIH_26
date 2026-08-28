import pytest
from vita.rgb.aggregator import FeatureAggregator


def test_median_aggregation():
    aggregator = FeatureAggregator(3)
    aggregator.add({"area": 100, "red": .4})
    aggregator.add({"area": 5000, "red": .5})
    aggregator.add({"area": 110, "red": .6})
    result = aggregator.aggregate()
    assert result["area_median"] == 110
    assert result["red_median"] == pytest.approx(.5)
    assert result["area_std"] > 0

