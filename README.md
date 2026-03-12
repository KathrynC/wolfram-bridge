# Wolfram Data Bridge

A robust Python interface to the **Wolfram Knowledgebase**, designed for fetching curated, computable data from the world's most comprehensive source of structured knowledge.

This tool was originally developed as part of the **NADJA** "Absolute Reality" engine to ground LLM-driven simulations in objective physics, geography, history, and math.

## Features

- **Grounded Facts:** Fetch ticker metadata, macro indicators, and geospatial data directly from Wolfram.
- **Biological & Neuro Grounding:** Query `AnatomicalStructure` for brain connectivity, `TaxonomicSpecies` for life-cycles, and `MetabolicPathway` for energy constraints.
- **Topological Analysis:** Compute path crossings and invariants for complex trajectories.
- **Geometric Reasoning:** Analyze polyhedral symmetry and convexity.
- **Cross-Domain Data:** Access specific data for anatomy, chemistry, linguistics, and celestial mechanics.
- **Intellectual Lineage:** Fetch birth/death dates and notable works for historical thinkers via `Person` data.
- **Sanitized Execution:** Bulletproof sanitization of Wolfram Language (WL) code to prevent command injection.
- **Computable Surrealism:** Tools for mapping mythological motifs to Thompson Motif-Index IDs.

## Installation

### Prerequisites

- **Wolfram Engine** or **Mathematica** must be installed.
- **wolframscript** must be available in your PATH.

### Basic Setup

```bash
pip install .
```

## Usage

```python
from wolfram_bridge import WolframDataBridge

bridge = WolframDataBridge()

# Fetch Ticker Metadata
spy_data = bridge.get_ticker_metadata("SPY")
print(spy_data["description"])

# Fetch Brain Connectivity (Dehaene enrichment)
amygdala = bridge.get_brain_connectivity("Amygdala")
print(f"Connections: {amygdala['connections']}, Volume: {amygdala['volume']}")

# Fetch Life Expectancy (Aging simulator grounding)
life = bridge.get_life_expectancy("UnitedStates", age=70)
print(f"Remaining Life Expectancy: {life['life_expectancy_years']} years")

# Fetch Thinker Metadata (Memory Palace Guardians)
euler = bridge.get_thinker_metadata("Leonhard Euler")
print(f"Notable Works: {euler['notable_works']}")

# Run Custom WL Expression
result = bridge.query_custom('ChemicalData["Ethanol", "BoilingPoint"]')
print(result)
```

## Running Tests

The bridge includes a comprehensive suite of offline (mocked) and live tests.

```bash
# Run offline tests
pytest tests/test_bridge.py

# Run live tests (requires wolframscript)
pytest tests/test_bridge.py -m live
```

## Why the Bridge?

In the context of LLM orchestration, "Data Cannibalism" occurs when models train on their own synthetic output, leading to epistemic decay. The **Wolfram Data Bridge** provides an "Epistemic Sanctuary"—a hard digestive floor of reality that prevents hallucinations by forcing the model to encounter computable, objective facts.

## License

MIT
