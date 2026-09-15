from metrics import Metrics


def test_slo_report_exposes_latency_and_availability():
    metrics = Metrics(sample_limit=100)
    for _ in range(25):
        metrics.inc("http_200")
        metrics.observe("http_latency_ms", 100.0)
    metrics.inc("http_500")
    metrics.observe("http_latency_ms", 2000.0)

    report = metrics.slo_report(
        availability_target=95.0,
        p95_latency_target_ms=500.0,
        minimum_requests=20,
    )

    assert report["requests"] == 26
    assert report["server_errors"] == 1
    assert report["status"] == "pass"
    assert report["latency_ms"]["p95"] == 100.0
    assert "orbythra_counter" in metrics.render_prometheus()


def test_slo_report_marks_small_samples_as_insufficient():
    metrics = Metrics()
    metrics.inc("http_200")
    metrics.observe("http_latency_ms", 50.0)
    assert metrics.slo_report(minimum_requests=20)["status"] == "insufficient_data"
