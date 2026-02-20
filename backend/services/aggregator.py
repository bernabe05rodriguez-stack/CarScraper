from backend.db.models import AuctionListing


def compute_auction_stats(listings: list[AuctionListing]) -> dict:
    """Compute aggregate statistics from auction listings."""
    if not listings:
        return {}

    sold = [l for l in listings if l.is_sold and l.sold_price]
    unsold = [l for l in listings if not l.is_sold]

    sold_prices = [l.sold_price for l in sold]
    starting_bids = [l.starting_bid for l in listings if l.starting_bid is not None]
    bid_counts = [l.bid_count for l in listings if l.bid_count is not None]
    auction_days = [l.auction_days for l in listings if l.auction_days is not None]

    stats = {
        "total_listings": len(listings),
        "total_sold": len(sold),
        "total_unsold": len(unsold),
        "sell_through_rate": round(len(sold) / len(listings) * 100, 1) if listings else 0,
    }

    if sold_prices:
        stats["mean_sold_price"] = round(sum(sold_prices) / len(sold_prices), 2)
        stats["median_sold_price"] = _median(sold_prices)
        stats["min_sold_price"] = min(sold_prices)
        stats["max_sold_price"] = max(sold_prices)

    if starting_bids:
        stats["mean_starting_bid"] = round(sum(starting_bids) / len(starting_bids), 2)
        stats["median_starting_bid"] = _median(starting_bids)

    if bid_counts:
        stats["mean_bids"] = round(sum(bid_counts) / len(bid_counts), 1)
        stats["median_bids"] = _median(bid_counts)

    if auction_days:
        stats["mean_auction_days"] = round(sum(auction_days) / len(auction_days), 1)
        stats["median_auction_days"] = _median(auction_days)

    return stats


def compute_used_car_stats(listings) -> dict:
    """Compute aggregate statistics from used car listings."""
    if not listings:
        return {}

    prices = [l.list_price for l in listings if l.list_price is not None]
    days = [l.days_on_market for l in listings if l.days_on_market is not None]
    mileages = [l.mileage for l in listings if l.mileage is not None]

    stats = {
        "total_listings": len(listings),
        "active_listings": sum(1 for l in listings if l.is_active),
    }

    if prices:
        stats["mean_list_price"] = round(sum(prices) / len(prices), 2)
        stats["median_list_price"] = _median(prices)
        stats["min_list_price"] = min(prices)
        stats["max_list_price"] = max(prices)

    if days:
        stats["mean_days_on_market"] = round(sum(days) / len(days), 1)
        stats["median_days_on_market"] = _median(days)

    if mileages:
        stats["mean_mileage"] = round(sum(mileages) / len(mileages), 0)
        stats["median_mileage"] = _median(mileages)

    return stats


def compute_comparison_stats(
    usa_listings,
    germany_listings,
    eur_usd_rate: float = 1.08,
) -> dict:
    """Compute comparison statistics between USA and Germany listings."""
    usa_prices = [l.list_price for l in usa_listings if l.list_price is not None]
    de_prices = [l.list_price for l in germany_listings if l.list_price is not None]

    usa_days = [l.days_on_market for l in usa_listings if l.days_on_market is not None]
    de_days = [l.days_on_market for l in germany_listings if l.days_on_market is not None]

    result = {
        "usa": {
            "count": len(usa_listings),
            "mean_price": round(sum(usa_prices) / len(usa_prices), 2) if usa_prices else None,
            "median_price": _median(usa_prices) if usa_prices else None,
            "min_price": min(usa_prices) if usa_prices else None,
            "max_price": max(usa_prices) if usa_prices else None,
            "mean_days_on_market": round(sum(usa_days) / len(usa_days), 1) if usa_days else None,
            "currency": "USD",
        },
        "germany": {
            "count": len(germany_listings),
            "mean_price_eur": round(sum(de_prices) / len(de_prices), 2) if de_prices else None,
            "median_price_eur": _median(de_prices) if de_prices else None,
            "min_price_eur": min(de_prices) if de_prices else None,
            "max_price_eur": max(de_prices) if de_prices else None,
            "mean_price_usd": round(sum(de_prices) / len(de_prices) * eur_usd_rate, 2) if de_prices else None,
            "median_price_usd": round(_median(de_prices) * eur_usd_rate, 2) if de_prices else None,
            "mean_days_on_market": round(sum(de_days) / len(de_days), 1) if de_days else None,
            "currency": "EUR",
        },
    }

    # Calculate price delta (USA - Germany in USD)
    usa_mean = result["usa"]["mean_price"]
    de_mean_usd = result["germany"]["mean_price_usd"]

    if usa_mean is not None and de_mean_usd is not None:
        delta = round(usa_mean - de_mean_usd, 2)
        delta_pct = round((delta / de_mean_usd) * 100, 1) if de_mean_usd != 0 else 0
        result["price_delta_usd"] = delta
        result["price_delta_pct"] = delta_pct
        result["arbitrage_direction"] = "Buy in Germany" if delta > 0 else "Buy in USA"
    else:
        result["price_delta_usd"] = None
        result["price_delta_pct"] = None
        result["arbitrage_direction"] = None

    result["eur_usd_rate"] = eur_usd_rate

    return result


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 2)
