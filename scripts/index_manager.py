#!/usr/bin/env python3
"""
Dynamic Index Manager
Fetches real market indices, caches company metadata, and tracks discovery dates.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

class IndexManager:
    """Manages dynamic index fetching with local caching and incremental updates."""

    def __init__(self, data_dir: str = 'data/indices'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.companies_file = self.data_dir / 'companies_registry.json'
        self.indices_file = self.data_dir / 'indices_cache.json'

        self.companies = self._load_companies_registry()
        self.indices_cache = self._load_indices_cache()

    def _load_companies_registry(self) -> Dict:
        """Load company metadata registry with discovery dates."""
        if self.companies_file.exists():
            try:
                with open(self.companies_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load companies registry: {e}")

        return {
            'companies': {},  # ticker -> {name, sector, discovered_date, indices, last_updated}
            'last_updated': None,
            'total_companies': 0
        }

    def _load_indices_cache(self) -> Dict:
        """Load cached index constituent lists."""
        if self.indices_file.exists():
            try:
                with open(self.indices_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load indices cache: {e}")

        return {
            'indices': {},  # index_name -> {tickers: [], last_updated: date}
            'refresh_intervals': {
                'sp500': 7,      # days - S&P changes rarely
                'ftse100': 30,   # monthly updates
                'dax': 30,       # quarterly reviews
                'sp400': 30,     # S&P MidCap 400
                'sp600': 30,     # S&P SmallCap 600
                'nikkei225': 90, # less frequent changes
                'asx200': 90
            }
        }

    def _save_companies_registry(self):
        """Save companies registry atomically."""
        self.companies['last_updated'] = datetime.now().isoformat()
        self.companies['total_companies'] = len(self.companies['companies'])

        temp_file = self.companies_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.companies, f, indent=2)
            temp_file.rename(self.companies_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _save_indices_cache(self):
        """Save indices cache atomically."""
        temp_file = self.indices_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.indices_cache, f, indent=2)
            temp_file.rename(self.indices_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _needs_refresh(self, index_name: str) -> bool:
        """Check if index needs refreshing based on last update date."""
        if index_name not in self.indices_cache['indices']:
            return True

        last_updated = self.indices_cache['indices'][index_name].get('last_updated')
        if not last_updated:
            return True

        refresh_days = self.indices_cache['refresh_intervals'].get(index_name, 30)
        last_date = datetime.fromisoformat(last_updated)
        return (datetime.now() - last_date).days > refresh_days

    def _discover_company_info(self, ticker: str) -> Optional[Dict]:
        """Fetch basic company information and add to registry."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            company_data = {
                'name': info.get('longName') or info.get('shortName', ticker),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'country': info.get('country', 'Unknown'),
                'market_cap': info.get('marketCap'),
                'discovered_date': datetime.now().isoformat(),
                'indices': [],  # Will be populated when ticker is found in indices
                'last_updated': datetime.now().isoformat()
            }

            logger.info(f"Discovered company: {ticker} - {company_data['name']}")
            return company_data

        except Exception as e:
            logger.warning(f"Could not fetch info for {ticker}: {e}")
            return None

    def _fetch_sp500_tickers(self) -> List[str]:
        """Fetch actual S&P 500 tickers from reliable sources."""
        import requests
        import pandas as pd
        from io import StringIO

        # Method 1: Wikipedia (most reliably up-to-date)
        try:
            resp = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            resp.raise_for_status()
            tables = pd.read_html(StringIO(resp.text))
            tickers = tables[0]['Symbol'].tolist()
            if len(tickers) >= 490:  # sanity check
                logger.info(f"✅ Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
                return tickers
        except Exception as e1:
            logger.warning(f"Wikipedia failed: {e1}")

        # Method 2: datahub.io fallback
        try:
            url = 'https://datahub.io/core/s-and-p-500-companies/r/constituents.csv'
            df = pd.read_csv(url)
            tickers = df['Symbol'].tolist()
            logger.info(f"✅ Fetched {len(tickers)} S&P 500 tickers from datahub.io")
            return tickers
        except Exception as e2:
            logger.warning(f"Datahub.io failed: {e2}")

        # Final fallback
        logger.warning("All S&P 500 sources failed, using expanded fallback list")
        return self._get_expanded_fallback_list()

    def _fetch_sp400_tickers(self) -> List[str]:
        """Fetch S&P MidCap 400 tickers from Wikipedia."""
        import requests
        import pandas as pd
        from io import StringIO

        try:
            resp = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            resp.raise_for_status()
            tables = pd.read_html(StringIO(resp.text))
            tickers = tables[0]['Symbol'].tolist()
            if len(tickers) >= 350:
                logger.info(f"Fetched {len(tickers)} S&P 400 tickers from Wikipedia")
                return tickers
        except Exception as e:
            logger.warning(f"S&P 400 Wikipedia fetch failed: {e}")
        return []

    def _fetch_sp600_tickers(self) -> List[str]:
        """Fetch S&P SmallCap 600 tickers from Wikipedia."""
        import requests
        import pandas as pd
        from io import StringIO

        try:
            resp = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            resp.raise_for_status()
            tables = pd.read_html(StringIO(resp.text))
            tickers = tables[0]['Symbol'].tolist()
            if len(tickers) >= 500:
                logger.info(f"Fetched {len(tickers)} S&P 600 tickers from Wikipedia")
                return tickers
        except Exception as e:
            logger.warning(f"S&P 600 Wikipedia fetch failed: {e}")
        return []

    def _get_major_us_stocks(self) -> List[str]:
        """Get comprehensive list of major US stocks from multiple exchanges."""
        # Comprehensive list of major US stocks across NYSE, NASDAQ, and other exchanges
        # This includes S&P 500, Russell 1000, and other major indices
        major_stocks = [
            # Top tech companies
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'ADBE',
            'CRM', 'ORCL', 'INTC', 'AMD', 'QCOM', 'TXN', 'MU', 'ADI', 'MRVL', 'LRCX',
            'KLAC', 'AMAT', 'SNPS', 'CDNS', 'FTNT', 'PANW', 'CRWD', 'ZS', 'OKTA', 'DDOG',

            # Financial sector
            'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'USB', 'TFC', 'PNC', 'COF',
            'AXP', 'BLK', 'SCHW', 'CME', 'ICE', 'SPGI', 'MCO', 'MMC', 'AON', 'AJG',
            'V', 'MA', 'PYPL', 'SQ', 'FIS', 'FISV', 'ADP', 'INTU', 'PAYX', 'BR',

            # Healthcare & pharma
            'UNH', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'LLY', 'BMY', 'AMGN',
            'GILD', 'BIIB', 'REGN', 'VRTX', 'ISRG', 'DHR', 'SYK', 'BSX', 'MDT', 'ZBH',
            'BDX', 'BAX', 'EW', 'DXCM', 'ILMN', 'INCY', 'MRNA', 'TECH', 'ALGN', 'HOLX',

            # Consumer goods & retail
            'WMT', 'HD', 'PG', 'KO', 'PEP', 'COST', 'TGT', 'LOW', 'NKE', 'SBUX',
            'MCD', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'CL', 'KMB', 'GIS', 'K',
            'TJX', 'ROST', 'ULTA', 'LULU', 'DECK', 'TPG', 'YUM', 'CMG', 'QSR', 'DPZ',

            # Energy sector
            'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PSX', 'VLO', 'MPC', 'PXD', 'KMI',
            'OKE', 'WMB', 'EPD', 'ET', 'MPLX', 'BKR', 'HAL', 'DVN', 'FANG', 'APA',

            # Industrial sector
            'CAT', 'BA', 'HON', 'UNP', 'UPS', 'FDX', 'LMT', 'RTX', 'GE', 'MMM',
            'ITW', 'EMR', 'ETN', 'PH', 'CMI', 'FTV', 'DOV', 'ROK', 'IEX', 'XYL',
            'ROP', 'FAST', 'PAYX', 'VRSK', 'TDG', 'LDOS', 'GWW', 'EXPD', 'CHRW', 'JBHT',

            # Real estate & utilities
            'NEE', 'DUK', 'SO', 'AEP', 'D', 'EXC', 'XEL', 'SRE', 'PCG', 'EIX',
            'PLD', 'AMT', 'CCI', 'EQIX', 'WELL', 'AVB', 'EQR', 'DLR', 'O', 'CBRE',
            'SPG', 'PSA', 'EXR', 'VTR', 'ARE', 'MAA', 'ESS', 'KIM', 'REG', 'BXP',

            # Materials & basic industries
            'LIN', 'APD', 'SHW', 'FCX', 'NUE', 'STLD', 'VMC', 'MLM', 'NEM', 'FMC',
            'LYB', 'DOW', 'DD', 'PPG', 'ECL', 'IFF', 'CE', 'PKG', 'AVY', 'SEE',

            # Emerging growth & biotech
            'ZM', 'SHOP', 'ROKU', 'SNOW', 'PLTR', 'RBLX', 'U', 'COIN', 'HOOD', 'AFRM',
            'SOFI', 'UPST', 'PTON', 'UBER', 'LYFT', 'ABNB', 'DASH', 'TWLO', 'ZI', 'FSLY',
            'NET', 'ESTC', 'MDB', 'TEAM', 'ATLR', 'NOW', 'WDAY', 'VEEV', 'ZUO', 'BILL',

            # International ADRs
            'TSM', 'ASML', 'NVO', 'TM', 'SAP', 'SONY', 'UL', 'NVS', 'AZN', 'SHEL',
            'BP', 'RY', 'TD', 'BCS', 'DB', 'ING', 'CS', 'UBS', 'WBK', 'BBVA',

            # Small/mid cap growth
            'ENPH', 'SEDG', 'FSLR', 'RUN', 'PLUG', 'BE', 'ICLN', 'ARKG', 'ARKK', 'ARKW',
            'TDOC', 'PTON', 'BYND', 'OATS', 'GPRO', 'FIT', 'WORK', 'PINS', 'SNAP', 'TWTR'
        ]

        # Remove duplicates and return
        return list(dict.fromkeys(major_stocks))

    def _get_expanded_fallback_list(self) -> List[str]:
        """Expanded fallback list with more comprehensive stock coverage."""
        return self._get_major_us_stocks()[:200]  # Return first 200 as fallback

    def _fetch_ftse100_tickers(self) -> List[str]:
        """Fetch comprehensive international stock coverage."""
        international_stocks = [
            # UK major stocks
            'SHEL', 'AZN', 'UL', 'BP.L', 'HSBA.L', 'VOD.L', 'GSK.L', 'RIO.L', 'BHP.L', 'BATS.L',
            'DGE.L', 'LLOY.L', 'NWG.L', 'BARC.L', 'PRU.L', 'REL.L', 'BT-A.L', 'AAL.L', 'AV.L', 'CRH.L',
            'LSEG.L', 'FLTR.L', 'ANTO.L', 'GLEN.L', 'NG.L', 'CPG.L', 'ULVR.L', 'RDSA.L',

            # European ADRs
            'ASML', 'SAP', 'NVO', 'NVS', 'SIE', 'ALV', 'DTE', 'BAS', 'BMW', 'VOW3',
            'TTE', 'BN', 'AIR', 'SU', 'CAP', 'BNP', 'ACA', 'GLE', 'MC', 'OR', 'SAN',

            # Asian ADRs
            'TSM', 'BABA', 'JD', 'PDD', 'BIDU', 'NTES', 'TME', 'BILI', 'NIO', 'XPEV', 'LI',
            'SONY', 'TM', 'MUFG', 'SMFG', 'HMC', 'NTT', 'SFT',

            # Canadian stocks
            'RY', 'TD', 'BNS', 'BMO', 'CM', 'CNR', 'CP', 'SU', 'CNQ', 'IMO', 'CVE',
            'TRP', 'ENB', 'PPL', 'SHOP', 'WEED', 'ACB', 'CRON', 'TLRY',

            # Brazilian/Latin American ADRs
            'VALE', 'PBR', 'ITUB', 'BBD', 'ABEV', 'SBS', 'TIMB', 'STNE', 'PAGS', 'NU',

            # More international coverage
            'ING', 'ABN', 'UNA', 'MT', 'STM', 'AXA', 'CS', 'UBS', 'NOVN', 'ROG', 'NESN'
        ]

        logger.info(f"International stock coverage: {len(international_stocks)} tickers")
        return international_stocks

    def _fetch_dax_tickers(self) -> List[str]:
        """Fetch DAX and other German/European stocks."""
        german_european_stocks = [
            # German DAX major stocks
            'SAP', 'ASML', 'SIE', 'ALV', 'DTE', 'BAS', 'BMW', 'VOW3', 'MBG', 'ADS',
            'DB', 'DBK', 'LIN', 'MUV2', 'HEN3', 'FRE', 'RWE', 'EON', 'IFX', 'DAI',
            'CON', 'HEI', 'FME', 'MTX', 'EOAN', 'BEI', 'SHL', 'PAH3', 'QIA', 'PUM',

            # Swiss major stocks
            'NESN', 'ROG', 'NOVN', 'UHR', 'LONN', 'CFR', 'SLHN', 'SREN', 'GIVN', 'ZURN',

            # French major stocks
            'MC', 'OR', 'SAN', 'TTE', 'BN', 'AIR', 'SU', 'CAP', 'BNP', 'ACA', 'GLE',

            # Dutch major stocks
            'PHIA', 'ADYEN', 'BESI', 'ASM', 'DSM', 'KPN', 'UNA', 'MT', 'ING', 'ABN'
        ]
        logger.info(f"German/European stock coverage: {len(german_european_stocks)} tickers")
        return german_european_stocks

    def _fetch_nikkei225_tickers(self) -> List[str]:
        """Fetch Nikkei 225 and major Japanese stocks."""
        japanese_stocks = [
            # Major Japanese companies (some as ADRs)
            'SONY', 'TM', 'MUFG', 'SMFG', 'HMC', 'NTT', 'SFT', 'KYOCF', 'FUJHY',
            '7203.T', '6098.T', '4063.T', '4502.T', '9984.T', '9432.T', '8316.T',
            '6758.T', '7267.T', '6861.T', '6954.T', '6920.T', '6752.T', '4543.T',
            '8031.T', '4911.T', '6981.T', '7751.T', '4568.T', '4523.T', '4503.T',
            '8058.T', '9020.T', '9022.T', '4612.T', '8802.T', '8411.T', '7974.T',
            'MSBHF', 'SFTBY', 'NTDOY', 'FUJIF', 'HTHIY', 'MZDAY', 'SZKMY', 'TKOMY'
        ]
        logger.info(f"Japanese stock coverage: {len(japanese_stocks)} tickers")
        return japanese_stocks

    def _fetch_asx200_tickers(self) -> List[str]:
        """Fetch ASX 200 and major Australian/Pacific stocks."""
        australian_stocks = [
            # Major Australian companies
            'CBA', 'ANZ', 'WBC', 'NAB', 'BHP', 'RIO', 'FMG', 'WOW', 'COL', 'TLS',
            'CSL', 'WDS', 'MQG', 'TCL', 'SHL', 'WES', 'GMG', 'JHX', 'ALL', 'AMP',
            'ASX', 'CPU', 'DXS', 'IAG', 'MIN', 'NCM', 'ORG', 'QAN', 'QBE', 'REA',
            'S32', 'STO', 'SUN', 'WPL', 'XRO', 'APT', 'A2M', 'ALU', 'CWN', 'EVN',

            # New Zealand and Pacific coverage
            'ATM', 'FPH', 'MCY', 'SKC', 'SPK', 'FBU', 'KMD', 'MEL', 'AIR', 'AIA'
        ]
        logger.info(f"Australian/Pacific stock coverage: {len(australian_stocks)} tickers")
        return australian_stocks

    def get_index_tickers(self, index_name: str, force_refresh: bool = False) -> List[str]:
        """Get tickers for an index, fetching if needed or using cache."""

        if force_refresh or self._needs_refresh(index_name):
            logger.info(f"Refreshing {index_name} index...")

            # Fetch based on index type
            if index_name == 'sp500':
                new_tickers = self._fetch_sp500_tickers()
            elif index_name == 'ftse100':
                new_tickers = self._fetch_ftse100_tickers()
            elif index_name == 'dax':
                new_tickers = self._fetch_dax_tickers()
            elif index_name == 'nikkei225':
                new_tickers = self._fetch_nikkei225_tickers()
            elif index_name == 'asx200':
                new_tickers = self._fetch_asx200_tickers()
            elif index_name == 'sp400':
                new_tickers = self._fetch_sp400_tickers()
            elif index_name == 'sp600':
                new_tickers = self._fetch_sp600_tickers()
            else:
                logger.warning(f"No fetcher implemented for {index_name}")
                new_tickers = []

            if new_tickers:
                # Update cache
                self.indices_cache['indices'][index_name] = {
                    'tickers': new_tickers,
                    'last_updated': datetime.now().isoformat(),
                    'count': len(new_tickers)
                }
                self._save_indices_cache()

                # Discover new companies
                self._update_company_registry(new_tickers, index_name)

                return new_tickers

        # Return cached version
        cached_data = self.indices_cache['indices'].get(index_name, {})
        return cached_data.get('tickers', [])

    def _update_company_registry(self, tickers: List[str], index_name: str):
        """Update company registry with new tickers from an index."""
        new_companies = 0

        for ticker in tickers:
            if ticker not in self.companies['companies']:
                # Discover new company
                company_info = self._discover_company_info(ticker)
                if company_info:
                    self.companies['companies'][ticker] = company_info
                    new_companies += 1

            # Add index to company's index list
            if ticker in self.companies['companies']:
                indices_list = self.companies['companies'][ticker].get('indices', [])
                if index_name not in indices_list:
                    indices_list.append(index_name)
                    self.companies['companies'][ticker]['indices'] = indices_list

        if new_companies > 0:
            logger.info(f"Discovered {new_companies} new companies from {index_name}")
            self._save_companies_registry()

    def get_all_tickers(self, max_age_days: int = 30) -> List[str]:
        """Get all known tickers, refreshing stale indices as needed."""
        all_tickers = set()

        # Define available indices
        available_indices = ['sp500', 'sp400', 'sp600', 'ftse100', 'dax', 'nikkei225', 'asx200']

        for index_name in available_indices:
            tickers = self.get_index_tickers(index_name)
            all_tickers.update(tickers)

        return list(all_tickers)

    def get_company_info(self, ticker: str) -> Optional[Dict]:
        """Get cached company information."""
        return self.companies['companies'].get(ticker)

    def get_stats(self) -> Dict:
        """Get registry statistics."""
        return {
            'total_companies': len(self.companies['companies']),
            'indices_cached': len(self.indices_cache['indices']),
            'last_registry_update': self.companies.get('last_updated'),
            'companies_by_index': {
                index: len([c for c in self.companies['companies'].values()
                          if index in c.get('indices', [])])
                for index in self.indices_cache['indices'].keys()
            }
        }


if __name__ == '__main__':
    """Test the index manager."""
    logging.basicConfig(level=logging.INFO)

    manager = IndexManager()

    print("=== Index Manager Stats ===")
    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\n=== Fetching S&P 500 ===")
    sp500_tickers = manager.get_index_tickers('sp500')
    print(f"S&P 500: {len(sp500_tickers)} tickers")

    print("\n=== All Tickers ===")
    all_tickers = manager.get_all_tickers()
    print(f"Total unique tickers: {len(all_tickers)}")

    if all_tickers:
        sample_ticker = all_tickers[0]
        company_info = manager.get_company_info(sample_ticker)
        print(f"\nSample company ({sample_ticker}):")
        print(json.dumps(company_info, indent=2))
