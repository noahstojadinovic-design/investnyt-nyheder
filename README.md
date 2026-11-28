# Nyheder til Makro Invest

Henter overskrifter fra officielle kilder (Danmarks Statistik, Nationalbanken, ECB, Fed, Bank of England, BLS, BEA)
og danske selskabsmeddelelser (GlobeNewswire) hvert kvarter og gemmer dem i `nyheder.json`.
Kun overskrift, tidspunkt, kilde og link. Siden investnyt.com læser filen.

Automatikken står i `.github/workflows/nyheder.yml`. Den kan også startes i hånden under Actions → Nyheder → Run workflow.
