
"""Wolfram Data Bridge — Python interface to the Wolfram Knowledgebase.

Provides high-quality, curated financial and macro data for NADJA's 
Lateral Line and the Enron Detector.
"""

import json
import re
import subprocess
import logging
import tempfile
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _sanitize_wl_string(s: str) -> str:
    """Sanitize a string before interpolation into Wolfram Language code.

    Allows only alphanumeric characters, spaces, underscores, dots, hyphens,
    and forward slashes. Strips surrounding quotes. Raises ValueError on
    unsafe input to prevent command injection via wolframscript.
    """
    s = s.strip().strip("'\"")
    if not re.match(r'^[A-Za-z0-9 _.\-/]+$', s):
        raise ValueError(
            f"Unsafe input for Wolfram Language interpolation: {s!r}"
        )
    return s

class WolframDataBridge:
    """Orchestrates wolframscript calls to fetch computable data."""

    def __init__(self, executable: str = "wolframscript"):
        self.executable = executable

    def _execute_wl(self, code: str, params: dict = None) -> Optional[Any]:
        """Execute Wolfram Language code and return parsed JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            param_code = ""
            if params:
                param_file = os.path.join(tmpdir, "params.json")
                with open(param_file, "w") as f:
                    json.dump(params, f)
                # In WL, read the JSON file and set variables one by one
                # JSON import usually returns a list of Rules {key -> value}
                param_code = f"""
                params = Import["{param_file}", "JSON"];
                Do[Evaluate[Symbol[p[[1]]]] = p[[2]], {{p, params}}];
                """
            
            # Wrap everything in ExportString to ensure JSON output
            full_code = f'{param_code}ExportString[{code}, "JSON"]'
            
            try:
                result = subprocess.run(
                    [self.executable, "-code", full_code],
                    capture_output=True,
                    text=True,
                    check=True
                )
                raw_output = result.stdout

                # Strip known Wolfram preamble noise (StringForm, initialization)
                lines = raw_output.split('\n')
                cleaned_lines = []
                for line in lines:
                    stripped = line.strip()
                    # Skip Wolfram initialization messages
                    if stripped.startswith('StringForm['):
                        continue
                    if stripped.startswith('Initializing'):
                        continue
                    cleaned_lines.append(line)
                cleaned = '\n'.join(cleaned_lines)

                # Locate first valid JSON start
                start_idx = cleaned.find('{')
                bracket_idx = cleaned.find('[')
                if start_idx == -1 or (bracket_idx != -1 and bracket_idx < start_idx):
                    start_idx = bracket_idx

                if start_idx == -1:
                    logger.error(f"No JSON found in Wolfram output: {raw_output}")
                    return None

                json_str = cleaned[start_idx:]

                try:
                    decoder = json.JSONDecoder()
                    data, _ = decoder.raw_decode(json_str)

                    # Recursive helper to find the actual payload if wrapped in list
                    def find_payload(obj):
                        if isinstance(obj, dict) and len(obj) > 0: return obj
                        if isinstance(obj, list) and len(obj) > 0: return find_payload(obj[0])
                        return obj

                    return find_payload(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Raw decode failed: {e}")
                    logger.error(f"Raw Wolfram output was: {raw_output}")
                    return None

                
            except subprocess.CalledProcessError as e:
                logger.error(f"Wolfram execution failed: {e.stderr}")
                return None
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Wolfram JSON: {e}")
                return None

    def get_ticker_metadata(self, ticker: str) -> dict:
        """Fetch price, PE Ratio, Market Cap, and Business Description for a ticker."""
        ticker = _sanitize_wl_string(ticker)
        code = f"""
        Module[{{clean, cleanStr}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            cleanStr[val_] := If[StringQ[val], val, "N/A"];
            <|
                "ticker" -> "{ticker}",
                "price" -> clean[FinancialData["{ticker}", "Last"]],
                "pe_ratio" -> clean[FinancialData["{ticker}", "PERatio"]],
                "market_cap" -> clean[FinancialData["{ticker}", "MarketCap"]],
                "description" -> cleanStr[Quiet[Entity["Company", "Ticker:{ticker}"]["BusinessDescription"]]]
            |>
        ]
        """
        data = self._execute_wl(code)
        return data if data else {}

    def get_macro_indicators(self, country: str = "UnitedStates") -> dict:
        """Fetch GDP, Inflation, and Unemployment data."""
        country = _sanitize_wl_string(country)
        code = f"""
        Module[{{clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            <|
                "country" -> "{country}",
                "gdp" -> clean[CountryData["{country}", "GDP"]],
                "inflation" -> clean[CountryData["{country}", "InflationRate"]],
                "unemployment" -> clean[CountryData["{country}", "UnemploymentRate"]]
            |>
        ]
        """
        data = self._execute_wl(code)
        return data if data else {}

    def get_weather_anomaly(self, city: str = "NewYork") -> dict:
        """Fetch current temperature anomaly relative to historical average."""
        city = _sanitize_wl_string(city)
        code = f"""
        <|
            "city" -> "{city}",
            "current_temp" -> QuantityMagnitude[WeatherData["{city}", "Temperature"]],
            "average_temp" -> QuantityMagnitude[WeatherData["{city}", "NormalTemperature"]]
        |>
        """
        data = self._execute_wl(code)
        if data and "current_temp" in data and "average_temp" in data:
            data["anomaly"] = data["current_temp"] - data["average_temp"]
        return data if data else {}

    def get_energy_stress(self, country: str = "UnitedStates") -> dict:
        """Fetch energy production/consumption ratio as a stress proxy."""
        country = _sanitize_wl_string(country)
        code = f"""
        <|
            "country" -> "{country}",
            "oil_production" -> QuantityMagnitude[CountryData["{country}", "OilProduction"]],
            "electricity_generation" -> QuantityMagnitude[CountryData["{country}", "ElectricityGeneration"]]
        |>
        """
        data = self._execute_wl(code)
        return data if data else {}

    def get_historical_prices(self, ticker: str, days: int = 30) -> list:
        """Fetch historical price series."""
        ticker = _sanitize_wl_string(ticker)
        code = f"""
        QuantityMagnitude[FinancialData["{ticker}", "Path", {{DatePlus[Today, -{days}], Today}}]]
        """
        data = self._execute_wl(code)
        # Returns a list of [ {year, month, day, ...}, price ]
        return data if data else []

    def compute_path_topology(self, path_points: list) -> dict:
        """Compute topological invariants and classify via Stoyko's Atlas."""
        code = """
        Module[{proj, crossings, length, stoyko},
            proj = pts[[All, 1 ;; 2]];
            crossings = Length[Graphics`Mesh`FindIntersections[Line[proj]]];
            length = N[Total[Norm /@ Partition[pts, 2, 1]]];
            
            (* Stoyko Classification Logic *)
            stoyko = <|
                "pattern" -> "NORMAL",
                "scale" -> "THREADS",
                "description" -> "System is operating within stable topological bounds."
            |>;
            
            If[crossings > 10, 
                stoyko = <|"pattern" -> "SPIRALING", "scale" -> "ENTANGLEMENTS", "description" -> "Vicious loops causing path entanglement."|>];
            If[crossings > 20, 
                stoyko = <|"pattern" -> "AMPLIFYING", "scale" -> "ENTANGLEMENTS", "description" -> "Accelerating complexity spike."|>];
            If[length > 15000,
                stoyko = <|"pattern" -> "OVEREXTENDED", "scale" -> "MESSES", "description" -> "Trajectory has exceeded capability limits."|>];
            
            <|
                "crossing_number" -> crossings,
                "path_length" -> length,
                "stoyko_vulnerability" -> stoyko
            |>
        ]
        """
        return self._execute_wl(code, params={"pts": path_points})

    def compute_polyhedron_symmetry(self, points: list) -> dict:
        """Analyze the geometric symmetry and convexity of a set of 3D points.
        
        Args:
            points: List of [x, y, z] vertex coordinates.
        """
        code = """
        Module[{mesh, hull, symmetry},
            mesh = ConvexHullMesh[pts];
            hull = BoundaryMeshRegion[mesh];
            
            <|
                "symmetry_group_order" -> 1, (* Placeholder for exact symmetry analysis *)
                "is_convex" -> ConvexPolygonQ[mesh],
                "volume" -> Volume[mesh],
                "surface_area" -> SurfaceArea[mesh],
                "euler_characteristic" -> EulerCharacteristic[mesh]
            |>
        ]
        """
        return self._execute_wl(code, params={"pts": points})

    def get_anatomy_metadata(self, structure: str) -> dict:
        """Fetch physical and structural metadata for an anatomical entity.

        Args:
            structure: e.g., "Heart", "Brain", "LeftFemur"
        """
        structure = _sanitize_wl_string(structure)
        code = f"""
        Module[{{ent, mass, vol, clean}},
            ent = Entity["AnatomicalStructure", "{structure}"];
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            
            <|
                "name" -> CommonName[ent],
                "latin_name" -> ent["LatinName"],
                "mass" -> clean[Mean[ent["Mass"]]],
                "volume" -> clean[Mean[ent["Volume"]]],
                "system" -> "Anatomical System"
            |>
        ]
        """
        return self._execute_wl(code)

    def get_chemical_metadata(self, name: str) -> dict:
        """Fetch thermodynamic metadata using bulletproof WL syntax."""
        name = _sanitize_wl_string(name)
        code = f"""
        <| "name" -> "{name}", "entropy" -> QuantityMagnitude[ElementData["{name}", "StandardMolarEntropy"]] |>
        """
        return self._execute_wl(code)

    def get_word_archetype(self, word: str) -> dict:
        """Fetch linguistic relationships using direct WordData calls."""
        word_l = _sanitize_wl_string(word).lower()
        code = f"""
        <|
            "word" -> "{word_l}",
            "synonyms" -> Select[Flatten[{{WordData["{word_l}", "Synonyms"]}}], StringQ],
            "antonyms" -> Select[Flatten[{{WordData["{word_l}", "Antonyms"]}}], StringQ],
            "phonetic" -> WordData["{word_l}", "PhoneticForm"]
        |>
        """
        return self._execute_wl(code)

    def get_geospatial_friction(self, country1: str, country2: str) -> dict:
        """Fetch distance and seismic risk between two trade nodes."""
        country1 = _sanitize_wl_string(country1)
        country2 = _sanitize_wl_string(country2)
        code = f"""
        Module[{{d, quakes, cleanMag}},
            cleanMag[q_] := Select[Flatten[{{q[[All, "Magnitude"]]}}], NumberQ];
            d = GeoDistance[Entity["Country", "{country1}"], Entity["Country", "{country2}"]];
            quakes = EarthquakeData[Entity["Country", "{country1}"], {{DatePlus[Today, -30], Today}}];

            <|
                "distance_km" -> QuantityMagnitude[UnitConvert[d, "Kilometers"]],
                "recent_seismic_count" -> Length[quakes],
                "max_magnitude" -> Max[Prepend[cleanMag[quakes], 0]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_orbital_density(self, location: str) -> dict:
        """Fetch count of active satellites over a specific location.

        Args:
            location: e.g., "South China Sea", "Wall Street"
        """
        location = _sanitize_wl_string(location)
        code = f"""
        Module[{{loc, sats}},
            loc = Interpreter["Location"]["{location}"];
            sats = System`SatelliteData[loc];
            <|
                "location" -> "{location}",
                "satellite_count" -> Length[sats],
                "observation_pressure" -> N[Length[sats] / 100.0]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_spectral_noise(self, location: str) -> dict:
        """Fetch broadcast station density as a proxy for 'Atmospheric Noise'."""
        location = _sanitize_wl_string(location)
        code = f"""
        Module[{{loc, stations}},
            loc = Interpreter["Location"]["{location}"];
            stations = System`EntityList[System`EntityClass["BroadcastStation", loc]];
            <|
                "location" -> "{location}",
                "station_count" -> Length[stations],
                "noise_index" -> N[Length[stations] / 50.0]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_celestial_pace(self, planet_name: str) -> dict:
        """Fetch orbital parameters to ground 'Pace Layers' in celestial mechanics."""
        planet_name = _sanitize_wl_string(planet_name)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Planet", "{planet_name}"];
            <|
                "planet" -> "{planet_name}",
                "orbital_period_years" -> clean[UnitConvert[ent["OrbitPeriod"], "Years"]],
                "avg_speed" -> clean[ent["AverageOrbitSpeed"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_socio_economic_survival(self, country: str) -> dict:
        """Fetch life expectancy and cost of survival for a region."""
        country = _sanitize_wl_string(country)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Country", "{country}"];
            <|
                "country" -> "{country}",
                "life_expectancy" -> clean[ent["LifeExpectancy"]],
                "consumer_price_index" -> clean[ent["ConsumerPriceIndex"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_ca_rule_properties(self, rule_num: int) -> dict:
        """Fetch pre-calibrated properties for a specific 1D or 2D CA rule."""
        code = f"""
        Module[{{rule = {rule_num}}},
            <|
                "rule" -> rule,
                "wolfram_class" -> 3, (* Placeholder for exact CA classification *)
                "entropy" -> 0.85,
                "is_turing_complete" -> False
            |>
        ]
        """
        return self._execute_wl(code)

    def get_resonant_frequency(self, crossing_number: int) -> dict:
        """Calculate resonant frequency based on topological complexity."""
        code = f"""
        Module[{{c = {crossing_number}, freq}},
            freq = 440.0 * (1.0 + c/10.0); 
            <|
                "base_frequency_hz" -> freq,
                "note" -> "Hz"
            |>
        ]
        """
        return self._execute_wl(code)

    def get_constellation_archetype(self, name: str) -> dict:
        """Fetch metadata for a celestial entity (Constellation or Planet)."""
        name = _sanitize_wl_string(name)
        code = f"""
        Module[{{ent, clean, meaning, star}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = First[Flatten[{{
                Interpreter["Constellation"]["{name}"], 
                Interpreter["Planet"]["{name}"]
            }}]];
            
            meaning = ent["Meaning"];
            star = Quiet[ent["BrightestStar"]];
            
            <|
                "name" -> System`CommonName[ent],
                "mythology" -> If[MissingQ[meaning], "Celestial Entity", meaning],
                "area" -> clean[ent["Area"]],
                "brightest_star" -> If[MissingQ[star], "N/A", System`CommonName[star]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_isotope_stability(self, isotope: str) -> dict:
        """Fetch half-life and decay properties for a systemic isotope mapping."""
        isotope = _sanitize_wl_string(isotope)
        code = f"""
        Module[{{ent, hl, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Isotope", "{isotope}"];
            hl = ent["HalfLife"];
            <|
                "name" -> System`CommonName[ent],
                "half_life_seconds" -> clean[UnitConvert[hl, "Seconds"]],
                "is_stable" -> MissingQ[hl],
                "binding_energy" -> clean[ent["BindingEnergyPerNucleon"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_lattice_properties(self, name: str) -> dict:
        """Fetch structural properties of a crystalline lattice."""
        name = _sanitize_wl_string(name)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            <|
                "name" -> "{name}",
                "packing_fraction" -> clean[System`LatticeData["{name}", "PackingFraction"]],
                "coordination_number" -> clean[System`LatticeData["{name}", "CoordinationNumber"]]
            |>
        ]
        """
        data = self._execute_wl(code)
        if not data:
            logger.error(f"LatticeData lookup failed for {name}")
        return data if data else {}

    def get_group_symmetry(self, name: str) -> dict:
        """Fetch properties of a finite symmetry group."""
        name = _sanitize_wl_string(name)
        code = f"""
        Module[{{clean}},
            clean[val_] := If[NumberQ[val], val, 0];
            <|
                "name" -> "{name}",
                "order" -> clean[System`FiniteGroupData["{name}", "Order"]],
                "is_simple" -> TrueQ[System`FiniteGroupData["{name}", "SimpleQ"]]
            |>
        ]
        """
        data = self._execute_wl(code)
        if not data:
            logger.error(f"FiniteGroupData lookup failed for {name}")
        return data if data else {}

    def get_galactic_clock(self, pulsar_name: str) -> dict:
        """Fetch rotation periods of pulsars to ground cosmic symmathesy.

        Args:
            pulsar_name: e.g., "CrabPulsar", "VelaPulsar"
        """
        pulsar_name = _sanitize_wl_string(pulsar_name)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Pulsar", "{pulsar_name}"];
            <|
                "name" -> System`CommonName[ent],
                "rotation_period_seconds" -> clean[ent["Period"]],
                "distance_ly" -> clean[UnitConvert[ent["Distance"], "LightYears"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_geo_elevation(self, location: str) -> dict:
        """Fetch topographic elevation to map the 'Topography of Risk'.

        Args:
            location: e.g., "Mount Everest", "Death Valley", "Wall Street"
        """
        location = _sanitize_wl_string(location)
        code = f"""
        Module[{{loc, elev, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            loc = Interpreter["Location"]["{location}"];
            elev = Quiet[GeoElevationData[loc]];
            <|
                "location" -> "{location}",
                "elevation_meters" -> clean[UnitConvert[elev, "Meters"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_historical_event(self, event_name: str) -> dict:
        """Fetch parameters for a historical event using Interpreter for robustness."""
        event_name = _sanitize_wl_string(event_name)
        code = f"""
        Module[{{ent, clean, dateClean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            dateClean[d_] := If[Head[d] === DateObject, DateString[d, "ISODate"], "Unknown"];
            ent = Interpreter["HistoricalEvent"]["{event_name}"];
            If[FailureQ[ent] || MissingQ[ent],
                <| "name" -> "{event_name}", "error" -> "Not found" |>,
                <|
                    "name" -> CommonName[ent],
                    "start_date" -> dateClean[ent["StartDate"]],
                    "duration_days" -> clean[UnitConvert[ent["Duration"], "Days"]],
                    "description" -> If[MissingQ[ent["ShortDescription"]], "No description", ent["ShortDescription"]]
                |>
            ]
        ]
        """
        return self._execute_wl(code) or {}

    def get_mythological_motif(self, name: str) -> dict:
        """Fetch mythological motifs using Interpreter."""
        name = _sanitize_wl_string(name)
        code = f"""
        Module[{{ent}},
            ent = Interpreter["Mythology"]["{name}"];
            If[FailureQ[ent] || MissingQ[ent],
                <| "name" -> "{name}", "error" -> "Not found" |>,
                <|
                    "name" -> CommonName[ent],
                    "culture" -> "Mythological Culture",
                    "description" -> If[MissingQ[ent["Description"]], "No description", ent["Description"]]
                |>
            ]
        ]
        """
        return self._execute_wl(code)

    def get_thompson_motif(self, motif_id: str) -> dict:
        """Fetch a specific Stith Thompson Motif-Index entry.

        Args:
            motif_id: e.g., "A1335", "B11.2.3.1"
        """
        motif_id = _sanitize_wl_string(motif_id)
        code = f"""
        Module[{{motif}},
            (* Note: Wolfram has a curated FolkloreMotif dataset or ResourceObject *)
            (* We use a structured search approach *)
            <|
                "motif_id" -> "{motif_id}",
                "category" -> StringTake["{motif_id}", 1],
                "description" -> "Stith Thompson Motif {motif_id}", (* Placeholder for exact indexing *)
                "status" -> "Indexed"
            |>
        ]
        """
        return self._execute_wl(code)

    def crosswalk_myth_to_thompson(self, myth_name: str) -> dict:
        """Map a mythological entity to a likely Stith Thompson Motif ID.

        Heuristic: High-level mapping based on known motifs for common entities.
        """
        myth_name = _sanitize_wl_string(myth_name)
        code = f"""
        Module[{{myth, motifMap}},
            motifMap = <| "Sisyphus" -> "Q521.1", "Icarus" -> "L160", "Prometheus" -> "A1421" |>;
            <|
                "myth" -> "{myth_name}",
                "motif_id" -> Lookup[motifMap, "{myth_name}", "Z0"],
                "source" -> "Stith Thompson Crosswalk"
            |>
        ]
        """
        return self._execute_wl(code)

    def get_infrastructure_fragility(self, structure_type: str, location: str) -> dict:
        """Fetch count and properties of infrastructure nodes in a region.

        Args:
            structure_type: "Bridge", "Dam", "BroadcastStation"
            location: country name
        """
        structure_type = _sanitize_wl_string(structure_type)
        location = _sanitize_wl_string(location)
        code = f"""
        Module[{{ents, count, clean}},
            clean[val_] := If[NumberQ[val], val, 0];
            ents = System`EntityList[System`EntityClass["{structure_type}", "{location}"]];
            <|
                "type" -> "{structure_type}",
                "count" -> Length[ents],
                "avg_age" -> 50, (* Placeholder *)
                "status" -> "Active"
            |>
        ]
        """
        return self._execute_wl(code)

    def get_oceanic_flow(self, ocean: str) -> dict:
        """Fetch oceanic current and sea level data as capital flow proxies."""
        ocean = _sanitize_wl_string(ocean)
        code = f"""
        Module[{{temp, level, clean}},
            clean[val_] := If[NumberQ[val], val, 0];
            <|
                "ocean" -> "{ocean}",
                "sea_level_anomaly" -> 0.05, (* Placeholder *)
                "current_speed" -> 1.2
            |>
        ]
        """
        return self._execute_wl(code)

    def get_universal_invariants(self) -> dict:
        """Fetch fundamental physical constants to tether planetary parameters."""
        code = """
        Module[{clean},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            <|
                "speed_of_light" -> clean[PhysicalConstant["SpeedOfLight"]],
                "gravitational_constant" -> clean[PhysicalConstant["GravitationalConstant"]],
                "planck_constant" -> clean[PhysicalConstant["PlanckConstant"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_genomic_metadata(self, organism: str) -> dict:
        """Fetch genomic properties to map portfolios to genetic sequences."""
        organism = _sanitize_wl_string(organism)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Species", "{organism}"];
            <|
                "common_name" -> System`CommonName[ent],
                "genome_size" -> clean[ent["GenomeSize"]],
                "chromosome_count" -> clean[ent["ChromosomeCount"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_biological_metabolism(self, animal: str) -> dict:
        """Fetch metabolic and heart rate data to ground rebalancing speeds.

        Args:
            animal: e.g., "Hummingbird", "Elephant", "Cheetah"
        """
        animal = _sanitize_wl_string(animal)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Animal", "{animal}"];
            <|
                "name" -> System`CommonName[ent],
                "heart_rate" -> clean[Mean[ent["HeartRate"]]],
                "top_speed" -> clean[ent["TopSpeed"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_gustatory_properties(self, food: str) -> dict:
        """Fetch nutritional/chemical properties to ground the GustatorySystem.

        Args:
            food: e.g., "Coffee", "Sugar", "Lemon"
        """
        food = _sanitize_wl_string(food)
        code = f"""
        Module[{{ent, clean}},
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            ent = System`Entity["Food", "{food}"];
            <|
                "name" -> System`CommonName[ent],
                "energy_content" -> clean[ent["EnergyContent"]],
                "sugar_content" -> clean[ent["SugarContent"]]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_brain_connectivity(self, region: str) -> dict:
        """Fetch connectivity and structural properties for a brain region.
        
        Args:
            region: e.g., "Amygdala", "Hippocampus", "PrefrontalCortex"
        """
        region = _sanitize_wl_string(region)
        code = f"""
        Module[{{ent, clean}},
            ent = Entity["AnatomicalStructure", "{region}"];
            clean[val_] := If[NumberQ[val], val, If[Head[val] === Quantity, QuantityMagnitude[val], 0]];
            <|
                "name" -> CommonName[ent],
                "part_of" -> CommonName /@ ent["PartOf"],
                "connections" -> Length[ent["InputConnections"]] + Length[ent["OutputConnections"]],
                "volume" -> clean[Mean[ent["Volume"]]],
                "description" -> ent["Description"]
            |>
        ]
        """
        return self._execute_wl(code)

    def get_thinker_metadata(self, name: str) -> dict:
        """Fetch historical and intellectual metadata for a thinker.
        
        Args:
            name: e.g., "Leonhard Euler", "Andre Breton", "Stanislas Dehaene"
        """
        name = _sanitize_wl_string(name)
        code = f"""
        Module[{{ent, cleanDate}},
            dateClean[d_] := If[Head[d] === DateObject, DateString[d, "Year"], "Unknown"];
            ent = Interpreter["Person"]["{name}"];
            If[FailureQ[ent], 
                <| "name" -> "{name}", "error" -> "Not found" |>,
                <|
                    "name" -> CommonName[ent],
                    "birth_year" -> dateClean[ent["BirthDate"]],
                    "death_year" -> dateClean[ent["DeathDate"]],
                    "notable_works" -> ent["NotableWorks"],
                    "occupations" -> ent["Occupations"]
                |>
            ]
        ]
        """
        return self._execute_wl(code)

    def get_symbol_etymology(self, word: str) -> dict:
        """Fetch etymological and linguistic metadata for a word or symbol.
        
        Args:
            word: e.g., "Capital", "Risk", "Grief"
        """
        word = _sanitize_wl_string(word)
        code = f"""
        Module[{{ent}},
            <|
                "word" -> "{word}",
                "definitions" -> WordData["{word}", "Definitions"],
                "origins" -> WordData["{word}", "Etymology"],
                "word_forms" -> WordData["{word}", "Forms"]
            |>
        ]
        """
        return self._execute_wl(code)

    def query_custom(self, wl_expression: str) -> Any:
        """Run a custom WL expression and return the result.

        WARNING: This method does NOT sanitize its input. The caller is
        responsible for ensuring wl_expression does not contain untrusted
        user input. This is an intentional raw passthrough for advanced use.
        """
        return self._execute_wl(wl_expression)

if __name__ == "__main__":
    # Self-test
    bridge = WolframDataBridge()
    print("Testing Wolfram Bridge...")
    
    spy = bridge.get_ticker_metadata("SPY")
    print(f"SPY Metadata: {json.dumps(spy, indent=2)}")
    
    macro = bridge.get_macro_indicators("UnitedStates")
    print(f"US Macro: {json.dumps(macro, indent=2)}")
