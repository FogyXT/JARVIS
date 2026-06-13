# Workflow Automation Concept (nedokončený / nedokonalý)

**Dátum:** 2025-04-08
**Stav:** Nápad, neimplementované — "nedokončený a nedokonalý concept"

## Cieľ

Jarvis ako univerzálny workflow executor — spúšťa reťazce úloh (PDF → scraper → Excel) na základe jednej vety. Fogy má už existujúce scripty na automatizáciu, toto by ich malo zjednotiť.

## Hlavná myšlienka

Namiesto 10 custom toolov jeden univerzálny `run_workflow(task)`.

## Navrhované komponenty

### 1. YAML workflow definície
Súbory v `D:/JARVIS/workflows/`:
```yaml
workflow: denny_reporting
steps:
  - task: "prehľadaj PDF v D:/data/pdf/"
    output: products.json
  - task: "scrapuj fotky z product_urls v products.json"
    output: photos/
  - task: "otvor template.xlsx, vyplň dáta z products.json"
    output: report_$(date).xlsx
```

### 2. Jeden tool "executor"
- `run_workflow(task_description)` — Jarvis si z pamäti alebo YAML súboru vytiahne čo robiť
- Poskladá príkazy, spustí existujúce scripty v správnom poradí
- Netreba meniť tooly keď sa zmení script

### 3. Error handling
- Ak scraper spadne na 3. produkte, pokračuje ďalej
- Na konci: "3 z 15 zlyhalo"
- Staré Excel neprepisovať — `report_2025-04-08_14-30.xlsx`

### 4. Logovanie + notifikácie
- Každý workflow loguje: čo sa stiahlo, čo sa vyplnilo, chyby
- Keď dobehne, DM na IG: "Report hotový, 15 produktov, 2 chyby"

### 5. Web UI dashboard (bonus)
- Tlačidlo "Spusti reporting"
- Status: BEŽÍ / HOTOVO / CHYBA
- Posledných 5 výsledkov

## Existujúce scripty (TODO: doplniť)

Fogy má už nejaké scripty na automatizáciu — treba zmapovať čo robia a napojiť.

## Poznámky

- Nepoužívať pevné cesty — každý workflow si vytvorí dočasný adresár
- Verzie súborov — staré neprepisovať
- Toto je len concept, nič nie je dokončené
