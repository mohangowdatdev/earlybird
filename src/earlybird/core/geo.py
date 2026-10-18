"""Countries, regions and tech-hub cities: the vocabulary for location eligibility and pickers.

Countries are ISO 3166-1 alpha-2 codes. Regions are the coarse groupings postings use
("Remote - EMEA", "anywhere in APAC"). Cities carry aliases so Bangalore == Bengaluru.
"""

import re
from functools import cache

COUNTRIES: dict[str, str] = {
    "IN": "India", "US": "United States", "CA": "Canada", "GB": "United Kingdom",
    "IE": "Ireland", "DE": "Germany", "FR": "France", "NL": "Netherlands", "ES": "Spain",
    "PT": "Portugal", "IT": "Italy", "PL": "Poland", "CH": "Switzerland", "SE": "Sweden",
    "DK": "Denmark", "NO": "Norway", "FI": "Finland", "BE": "Belgium", "AT": "Austria",
    "CZ": "Czechia", "RO": "Romania", "GR": "Greece", "HU": "Hungary", "UA": "Ukraine",
    "EE": "Estonia", "LT": "Lithuania", "IL": "Israel", "AE": "United Arab Emirates",
    "SA": "Saudi Arabia", "QA": "Qatar", "EG": "Egypt", "TR": "Turkey", "SG": "Singapore",
    "JP": "Japan", "KR": "South Korea", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan",
    "AU": "Australia", "NZ": "New Zealand", "MY": "Malaysia", "ID": "Indonesia",
    "PH": "Philippines", "VN": "Vietnam", "TH": "Thailand", "PK": "Pakistan",
    "BD": "Bangladesh", "LK": "Sri Lanka", "BR": "Brazil", "MX": "Mexico", "AR": "Argentina",
    "CO": "Colombia", "CL": "Chile", "PE": "Peru", "UY": "Uruguay", "CR": "Costa Rica",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
}  # fmt: skip

_EUROPE = {"GB", "IE", "DE", "FR", "NL", "ES", "PT", "IT", "PL", "CH", "SE", "DK", "NO", "FI",
           "BE", "AT", "CZ", "RO", "GR", "HU", "UA", "EE", "LT"}  # fmt: skip
_MIDDLE_EAST = {"IL", "AE", "SA", "QA", "EG", "TR"}
_AFRICA = {"EG", "ZA", "NG", "KE"}
_LATAM = {"BR", "MX", "AR", "CO", "CL", "PE", "UY", "CR"}
_APAC = {"IN", "SG", "JP", "KR", "CN", "HK", "TW", "AU", "NZ", "MY", "ID", "PH", "VN", "TH",
         "PK", "BD", "LK"}  # fmt: skip

REGIONS: dict[str, frozenset[str]] = {
    "worldwide": frozenset(COUNTRIES),
    "north_america": frozenset({"US", "CA"}),
    "americas": frozenset({"US", "CA"} | _LATAM),
    "latam": frozenset(_LATAM),
    "europe": frozenset(_EUROPE),
    "emea": frozenset(_EUROPE | _MIDDLE_EAST | _AFRICA),
    "middle_east": frozenset(_MIDDLE_EAST),
    "africa": frozenset(_AFRICA),
    "apac": frozenset(_APAC),
    "asia": frozenset(_APAC - {"AU", "NZ"}),
    "oceania": frozenset({"AU", "NZ"}),
}

# (canonical name, country, aliases)
CITIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Bengaluru", "IN", ("bangalore", "bengaluru")), ("Hyderabad", "IN", ()),
    ("Pune", "IN", ()), ("Chennai", "IN", ("madras",)), ("Mumbai", "IN", ("bombay",)),
    ("Delhi", "IN", ("new delhi", "delhi ncr", "ncr")), ("Gurugram", "IN", ("gurgaon",)),
    ("Noida", "IN", ()), ("Kolkata", "IN", ("calcutta",)), ("Ahmedabad", "IN", ()),
    ("Kochi", "IN", ("cochin",)), ("Coimbatore", "IN", ()), ("Jaipur", "IN", ()),
    ("Chandigarh", "IN", ()), ("Thiruvananthapuram", "IN", ("trivandrum",)),
    ("Indore", "IN", ()), ("Mysuru", "IN", ("mysore",)),
    ("San Francisco", "US", ("sf", "san francisco bay area", "bay area")),
    ("San Jose", "US", ()), ("Mountain View", "US", ()), ("Palo Alto", "US", ()),
    ("Sunnyvale", "US", ()), ("Menlo Park", "US", ()), ("Seattle", "US", ()),
    ("Redmond", "US", ()), ("New York", "US", ("new york city", "nyc")),
    ("Austin", "US", ()), ("Boston", "US", ()), ("Los Angeles", "US", ("la",)),
    ("Chicago", "US", ()), ("Denver", "US", ()), ("Washington", "US", ("washington dc", "dc")),
    ("Atlanta", "US", ()), ("Dallas", "US", ()), ("Raleigh", "US", ()),
    ("San Diego", "US", ()), ("Toronto", "CA", ()), ("Vancouver", "CA", ()),
    ("Montreal", "CA", ("montréal",)), ("Ottawa", "CA", ()), ("Waterloo", "CA", ()),
    ("London", "GB", ()), ("Manchester", "GB", ()), ("Edinburgh", "GB", ()),
    ("Cambridge", "GB", ()), ("Dublin", "IE", ()), ("Berlin", "DE", ()),
    ("Munich", "DE", ("münchen",)), ("Hamburg", "DE", ()), ("Frankfurt", "DE", ()),
    ("Paris", "FR", ()), ("Amsterdam", "NL", ()), ("Madrid", "ES", ()),
    ("Barcelona", "ES", ()), ("Lisbon", "PT", ("lisboa",)), ("Warsaw", "PL", ("warszawa",)),
    ("Krakow", "PL", ("kraków",)), ("Zurich", "CH", ("zürich",)), ("Stockholm", "SE", ()),
    ("Copenhagen", "DK", ()), ("Tel Aviv", "IL", ("tel aviv-yafo",)), ("Dubai", "AE", ()),
    ("Abu Dhabi", "AE", ()), ("Riyadh", "SA", ()), ("Doha", "QA", ()),
    ("Singapore", "SG", ()), ("Tokyo", "JP", ()), ("Seoul", "KR", ()),
    ("Shanghai", "CN", ()), ("Beijing", "CN", ()), ("Hong Kong", "HK", ()),
    ("Sydney", "AU", ()), ("Melbourne", "AU", ()), ("Auckland", "NZ", ()),
    ("Kuala Lumpur", "MY", ()), ("Jakarta", "ID", ()), ("Manila", "PH", ()),
    ("Ho Chi Minh City", "VN", ("saigon",)), ("Bangkok", "TH", ()),
    ("São Paulo", "BR", ("sao paulo",)), ("Mexico City", "MX", ("cdmx",)),
    ("Buenos Aires", "AR", ()), ("Bogotá", "CO", ("bogota",)), ("Santiago", "CL", ()),
    ("Cape Town", "ZA", ()), ("Johannesburg", "ZA", ()), ("Lagos", "NG", ()),
    ("Nairobi", "KE", ()), ("Cairo", "EG", ()), ("Istanbul", "TR", ()),
)  # fmt: skip

_SPACES = re.compile(r"\s+")


def _key(name: str) -> str:
    return _SPACES.sub(" ", name.strip().lower().replace(".", ""))


@cache
def _city_index() -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for name, country, aliases in CITIES:
        for alias in (name, *aliases):
            index[_key(alias)] = (name, country)
    return index


def canonical_city(name: str) -> tuple[str, str | None]:
    """`"bangalore"` -> `("Bengaluru", "IN")`. Unknown cities keep their name, country None."""
    found = _city_index().get(_key(name.split(",", maxsplit=1)[0]))
    return found if found else (name.strip(), None)


def country_code(name: str) -> str | None:
    """Accepts `IN`, `India`, `india`; returns the ISO code if known."""
    cleaned = name.strip()
    if cleaned.upper() in COUNTRIES:
        return cleaned.upper()
    lowered = cleaned.lower()
    for code, label in COUNTRIES.items():
        if label.lower() == lowered:
            return code
    aliases = {"usa": "US", "uk": "GB", "uae": "AE", "england": "GB", "korea": "KR"}
    return aliases.get(lowered)


def countries_in(regions: list[str]) -> set[str]:
    return set().union(*(REGIONS.get(r, frozenset()) for r in regions)) if regions else set()


def country_options() -> list[dict[str, str]]:
    """Picker suggestions: every country, grouped by its main region."""
    order = [("apac", "Asia-Pacific"), ("north_america", "North America"),
             ("europe", "Europe"), ("middle_east", "Middle East"), ("latam", "Latin America"),
             ("africa", "Africa")]  # fmt: skip
    seen: set[str] = set()
    options = []
    for region, label in order:
        for code in sorted(REGIONS[region] - seen, key=lambda c: COUNTRIES[c]):
            options.append({"value": code, "label": COUNTRIES[code], "group": label})
            seen.add(code)
    return options


def city_options() -> list[dict[str, str]]:
    """Picker suggestions: tech-hub cities grouped by country, India first."""
    ordered = sorted(CITIES, key=lambda c: (c[1] != "IN", COUNTRIES[c[1]], c[0]))
    return [{"value": name, "label": name, "group": COUNTRIES[country]}
            for name, country, _ in ordered]  # fmt: skip
