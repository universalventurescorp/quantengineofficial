"""What the channel can chart: curated, verified public data series.

Claude only ever picks keys from this catalog, so it can never invent a data source.
Add a series by adding one line (check the FRED id at fred.stlouisfed.org first).

unit: pct | pp (percentage points) | usd | usd_bn | usd_mn | thousands | index | ratio | usd_per_eur
transform: level | yoy (percent change from a year earlier) | div1000 (millions -> billions etc.)
"""

FRED = {
    # key: (FRED id, chart title, unit, transform, source, first year to show)
    "inflation":            ("CPIAUCSL", "US inflation rate (CPI, year over year)", "pct", "yoy", "U.S. Bureau of Labor Statistics", 1960),
    "core_inflation":       ("CPILFESL", "US core inflation (excl. food & energy)", "pct", "yoy", "U.S. Bureau of Labor Statistics", 1960),
    "cpi_index":            ("CPIAUCSL", "US consumer price index (1982-84 = 100)", "index", "level", "U.S. Bureau of Labor Statistics", 1950),
    "core_pce":             ("PCEPILFE", "US core PCE inflation (the Fed's target gauge)", "pct", "yoy", "U.S. Bureau of Economic Analysis", 1960),
    "food_at_home":         ("CUSR0000SAF11", "US grocery prices (year over year)", "pct", "yoy", "U.S. Bureau of Labor Statistics", 1970),
    "rent_inflation":       ("CUSR0000SEHA", "US rent inflation (year over year)", "pct", "yoy", "U.S. Bureau of Labor Statistics", 1985),
    "egg_price":            ("APU0000708111", "Average price of a dozen eggs in the US", "usd", "level", "U.S. Bureau of Labor Statistics", 1980),
    "bread_price":          ("APU0000702111", "Average price of a pound of white bread in the US", "usd", "level", "U.S. Bureau of Labor Statistics", 1980),
    "gas_price":            ("GASREGW", "US regular gasoline price (per gallon)", "usd", "level", "U.S. Energy Information Administration", 1991),
    "oil_price":            ("DCOILWTICO", "Crude oil price (WTI, per barrel)", "usd", "level", "U.S. Energy Information Administration", 1986),
    "unemployment":         ("UNRATE", "US unemployment rate", "pct", "level", "U.S. Bureau of Labor Statistics", 1948),
    "participation":        ("CIVPART", "US labor force participation rate", "pct", "level", "U.S. Bureau of Labor Statistics", 1948),
    "payrolls":             ("PAYEMS", "US nonfarm jobs", "thousands", "level", "U.S. Bureau of Labor Statistics", 1950),
    "job_openings":         ("JTSJOL", "US job openings", "thousands", "level", "U.S. Bureau of Labor Statistics", 2001),
    "jobless_claims":       ("ICSA", "US initial jobless claims (weekly)", "count", "level", "U.S. Department of Labor", 1967),
    "wages":                ("CES0500000003", "US average hourly earnings", "usd", "level", "U.S. Bureau of Labor Statistics", 2006),
    "wage_growth":          ("CES0500000003", "US wage growth (year over year)", "pct", "yoy", "U.S. Bureau of Labor Statistics", 2007),
    "median_income":        ("MEHOINUSA646N", "US median household income (nominal)", "usd", "level", "U.S. Census Bureau", 1984),
    "real_median_income":   ("MEHOINUSA672N", "US real median household income (inflation-adjusted)", "usd", "level", "U.S. Census Bureau", 1984),
    "saving_rate":          ("PSAVERT", "US personal saving rate", "pct", "level", "U.S. Bureau of Economic Analysis", 1959),
    "fed_funds":            ("FEDFUNDS", "Federal funds rate", "pct", "level", "Federal Reserve", 1954),
    "treasury_10y":         ("DGS10", "10-year US Treasury yield", "pct", "level", "Federal Reserve", 1962),
    "treasury_2y":          ("DGS2", "2-year US Treasury yield", "pct", "level", "Federal Reserve", 1976),
    "treasury_1y":          ("DGS1", "1-year US Treasury yield", "pct", "level", "Federal Reserve", 1962),
    "yield_curve":          ("T10Y2Y", "Yield curve: 10-year minus 2-year Treasury", "pp", "level", "Federal Reserve Bank of St. Louis", 1976),
    "mortgage_rate":        ("MORTGAGE30US", "30-year fixed mortgage rate", "pct", "level", "Freddie Mac", 1971),
    "home_price":           ("MSPUS", "Median price of a US home sold", "usd", "level", "U.S. Census Bureau / HUD", 1963),
    "case_shiller":         ("CSUSHPINSA", "Case-Shiller US home price index", "index", "level", "S&P Dow Jones Indices", 1987),
    "housing_starts":       ("HOUST", "US housing starts (annual rate)", "thousands", "level", "U.S. Census Bureau", 1959),
    "real_gdp":             ("GDPC1", "US real GDP (chained 2017 dollars)", "usd_bn", "level", "U.S. Bureau of Economic Analysis", 1947),
    "gdp_growth":           ("GDPC1", "US real GDP growth (year over year)", "pct", "yoy", "U.S. Bureau of Economic Analysis", 1948),
    "nominal_gdp":          ("GDP", "US nominal GDP", "usd_bn", "level", "U.S. Bureau of Economic Analysis", 1947),
    "potential_gdp":        ("GDPPOT", "US potential real GDP (CBO estimate)", "usd_bn", "level", "Congressional Budget Office", 1949),
    "gdp_per_capita":       ("A939RX0Q048SBEA", "US real GDP per person", "usd", "level", "U.S. Bureau of Economic Analysis", 1947),
    "federal_debt":         ("GFDEBTN", "US federal debt", "usd_bn", "div1000", "U.S. Department of the Treasury", 1966),
    "debt_to_gdp":          ("GFDEGDQ188S", "US federal debt as a share of GDP", "pct", "level", "Federal Reserve Bank of St. Louis / OMB", 1966),
    "interest_payments":    ("A091RC1Q027SBEA", "US federal interest payments (annual rate)", "usd_bn", "level", "U.S. Bureau of Economic Analysis", 1947),
    "deficit":              ("FYFSD", "US federal surplus or deficit", "usd_bn", "div1000", "U.S. Office of Management and Budget", 1950),
    "m2":                   ("M2SL", "US money supply (M2)", "usd_bn", "level", "Federal Reserve", 1959),
    "m2_growth":            ("M2SL", "US money supply growth (M2, year over year)", "pct", "yoy", "Federal Reserve", 1960),
    "fed_balance_sheet":    ("WALCL", "Federal Reserve balance sheet", "usd_bn", "div1000", "Federal Reserve", 2003),
    "sp500":                ("SP500", "S&P 500 index", "index", "level", "S&P Dow Jones Indices", 2016),
    "nasdaq":               ("NASDAQCOM", "Nasdaq Composite index", "index", "level", "Nasdaq", 1971),
    "vix":                  ("VIXCLS", "VIX: stock market fear index", "index", "level", "Cboe", 1990),
    "dollar_index":         ("DTWEXBGS", "US dollar index (broad, trade-weighted)", "index", "level", "Federal Reserve", 2006),
    "eur_usd":              ("DEXUSEU", "Dollars per euro", "usd_per_eur", "level", "Federal Reserve", 1999),
    "consumer_sentiment":   ("UMCSENT", "Consumer sentiment (University of Michigan)", "index", "level", "University of Michigan", 1978),
    "retail_sales":         ("RSXFS", "US retail sales (monthly)", "usd_mn", "level", "U.S. Census Bureau", 1992),
    "industrial_production": ("INDPRO", "US industrial production index", "index", "level", "Federal Reserve", 1950),
    "consumer_credit":      ("TOTALSL", "US consumer credit outstanding", "usd_bn", "level", "Federal Reserve", 1950),
    "credit_card_rate":     ("TERMCBCCALLNSA", "Average credit card interest rate", "pct", "level", "Federal Reserve", 1995),
    "card_delinquency":     ("DRCCLACBS", "Credit card delinquency rate", "pct", "level", "Federal Reserve", 1991),
    "debt_service":         ("TDSP", "Household debt payments as a share of income", "pct", "level", "Federal Reserve", 1980),
}

RECESSIONS_FRED = "USREC"       # 1 during NBER recessions; used to shade charts

WB_INDICATORS = {
    # key: (World Bank id, chart title, unit)
    "wb_gdp_per_capita":  ("NY.GDP.PCAP.CD", "GDP per person (current US dollars)", "usd"),
    "wb_gdp_growth":      ("NY.GDP.MKTP.KD.ZG", "Real GDP growth", "pct"),
    "wb_inflation":       ("FP.CPI.TOTL.ZG", "Inflation (consumer prices)", "pct"),
    "wb_unemployment":    ("SL.UEM.TOTL.ZS", "Unemployment rate", "pct"),
    "wb_gov_debt":        ("GC.DOD.TOTL.GD.ZS", "Central government debt (% of GDP)", "pct"),
    "wb_trade":           ("NE.TRD.GNFS.ZS", "Trade (% of GDP)", "pct"),
    "wb_savings":         ("NY.GNS.ICTR.ZS", "Gross savings (% of GDP)", "pct"),
    "wb_population":      ("SP.POP.TOTL", "Population", "count"),
    "wb_gdp":             ("NY.GDP.MKTP.CD", "GDP (current US dollars)", "usd"),
}

COUNTRIES = {
    "USA": "United States", "CHN": "China", "JPN": "Japan", "DEU": "Germany", "GBR": "United Kingdom",
    "FRA": "France", "IND": "India", "BRA": "Brazil", "CAN": "Canada", "KOR": "South Korea",
    "MEX": "Mexico", "ARG": "Argentina", "CHL": "Chile", "PER": "Peru", "COL": "Colombia",
    "ESP": "Spain", "ITA": "Italy", "AUS": "Australia", "TUR": "Turkey", "ZAF": "South Africa",
    "NGA": "Nigeria", "IDN": "Indonesia", "SAU": "Saudi Arabia", "CHE": "Switzerland",
    "SGP": "Singapore", "NOR": "Norway", "IRL": "Ireland", "VNM": "Vietnam", "POL": "Poland",
    "SWE": "Sweden", "ISR": "Israel", "EGY": "Egypt", "VEN": "Venezuela", "GRC": "Greece",
}


def catalog_for_prompt():
    """Compact catalog text for Claude."""
    lines = ["US data series (key: description [unit]):"]
    lines += [f"- {k}: {v[1]} [{v[2]}], from {v[5]}" for k, v in FRED.items()]
    lines.append("\nCountry comparison indicators (World Bank, annual), use as wb_key:ISO3, e.g. wb_inflation:ARG")
    lines += [f"- {k}: {v[1]} [{v[2]}]" for k, v in WB_INDICATORS.items()]
    lines.append("Countries: " + ", ".join(f"{k}={v}" for k, v in COUNTRIES.items()))
    return "\n".join(lines)


def is_valid_key(key):
    if key in FRED or key.startswith("calc:"):
        return True
    if ":" in key:
        ind, iso = key.split(":", 1)
        return ind in WB_INDICATORS and iso in COUNTRIES
    return False
