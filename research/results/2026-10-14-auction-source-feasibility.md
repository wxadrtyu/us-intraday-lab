# Five-minute auction-data source feasibility (read-only)

Status: source reconnaissance only. No historical data was purchased or
downloaded, no strategy returns were read, and no execution system was touched.

## Existing gate

The frozen Alpaca SIP five-minute audit remains the controlling negative
result: 19/20 fixed signal-entry-exit paths miss the 95% aggregate coverage
floor; the sole aggregate pass misses the monthly floor in 37/96 months.
This source cannot be rescued by picking that path, imputing missing prices,
or splicing in another provider. The quote/trade-only research family is
already exhausted; auction imbalance would have to be a genuinely different
signal contract, not a renamed version of that family.

## Source candidates and entitlement

* [NYSE historical data](https://www.nyse.com/market-data/historical/)
  lists separate end-of-day historical order-imbalance products for NYSE,
  NYSE American, and NYSE Arca. The [order-imbalance product page](https://beta.nyse.com/market-data/historical/taq-order-imbalances)
  dates those three histories to 2008, 2008, and 2012 respectively and
  presents them as purchase products. These are venue-specific, not proof of
  full-market point-in-time coverage. The published [NYSE historical price
  sheet](https://www.nyse.com/publicdocs/nyse/data/NYSE_Historical_Market_Data_Pricing.pdf)
  lists a charge for historical NYSE order-imbalance content; the exact
  applicable quote and license would need confirmation before ordering.
* [Databento Nasdaq TotalView-ITCH](https://databento.com/datasets/XNAS.ITCH)
  and [NYSE Integrated](https://databento.com/datasets/nyse-integrated)
  advertise normalized historical imbalance records. The venue pages date
  their dataset histories from 2018-05-01 but warn that availability can
  differ by schema. Nasdaq's documented opening/closing NOII messages start
  at 09:25/15:50 ET, and its near/far indicative clearing prices are not
  populated before 09:28/15:55 ET. A signal using those prices cannot be
  timestamped earlier. NYSE closing imbalance starts at 15:50 ET. These
  auction windows are not a general intraday five-minute feed.
* Databento's [historical API](https://databento.com/docs/api-reference-historical)
  offers entitlement-specific dataset-range/schema discovery and a cost
  estimate before download. Metadata and cost queries are described as free,
  but they still require an API key. The local process has no
  `DATABENTO_API_KEY`; no local historical auction-imbalance files were found.
  Existing Polygon/Massive credentials do not confer this entitlement, and
  the previous historical aggregate probe was 403 NOT_AUTHORIZED. No suitable
  Databento/NYSE/Nasdaq plugin connection was found in the available directory.

## Bounded validation before any bulk acquisition

1. Confirm account entitlement, per-schema historical date range, publisher
   venues, and estimated cost with metadata-only calls. Do not purchase or
   stream time series merely to discover the price.
2. Map the frozen point-in-time `monthly_universe_sip_v2` identities to their
   primary listing venues as of each sampled session. The source must cover
   every material listing venue, including delisted and renamed securities;
   venue marketing claims and a few sample symbols are insufficient.
3. Pre-register a small set of sessions across years and liquidity strata,
   then audit actual imbalance timestamps, missing symbols, and all exact
   signal-entry-exit timestamps for five- and ten-minute holds. The source
   must itself supply a defensible executable price path; an indicative
   auction price or no-trade interval is not an executable fill. Missing
   observations remain in the denominator.
4. Only if the same independent source passes the fixed >=95% aggregate and
   monthly coverage requirements, estimate full-history spend and request
   approval before any material download. The 2021-2026 periods already
   inspected stay consumed and cannot become independent OOS.

Until entitlement and this bounded audit exist, the data gate stays closed.
The actionable dependency is a locally configured historical-data API key
with the relevant auction venues enabled, plus a spending ceiling. No account
creation, subscription, purchase, or charge was authorized in this stage.
