from retailpulse.batch import prepare_uci


def test_prepare_normalizes_source_csv(tmp_path) -> None:
    source = tmp_path / "source.csv"
    source.write_text(
        "InvoiceNo,StockCode,Description,Quantity,InvoiceDate,UnitPrice,CustomerID,Country\n"
        "536365,85123A,HEART,6,12/1/2010 8:26,2.55,17850,United Kingdom\n"
        "C536366,85123A,HEART,-1,12/1/2010 9:00,2.55,17850,United Kingdom\n",
        encoding="utf-8",
    )
    counts = prepare_uci(source, tmp_path / "landing")
    assert counts == {"customers": 1, "products": 1, "orders": 2, "order_items": 2}
    assert '"is_cancelled":"true"' in (tmp_path / "landing" / "orders.jsonl").read_text()
