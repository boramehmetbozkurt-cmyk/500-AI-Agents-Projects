# OSIRIS Temporal Reality Atlas

OSIRIS Temporal Reality Atlas is the spatial-state layer of OSIRIS World. It provides a common, evidence-aware model for historical reconstruction, present physical reality, digital twins, mixed reality, metaverse spaces and future/counterfactual simulations.

## Core invariants

1. Time is first-class: every feature may carry a validity interval.
2. Negative years are BCE, positive years CE; year zero is rejected.
3. Approximate/disputed historical dates retain their uncertainty.
4. Canonical reality, reconstruction, plans and simulations are separate truth modes.
5. A future state cannot be inserted as a fact on canonical reality.
6. World Forks may add scenarios but cannot create canonical facts.
7. Physical and virtual spaces have explicit coordinate-space IDs.
8. Facts require evidence IDs; reality-branch reconstructions/plans require evidence or sources.
9. Every persisted feature is tenant-scoped.
10. Remote 3D assets are references with provenance/checksum metadata, not implicitly trusted executable content.

## Temporal model

`HistoricalDate` stores signed year, optional month/day, precision, certainty, calendar and uncertainty. Precision can be day, month, year, decade, century, millennium or unknown. Certainty can be exact, circa, estimated, earliest, latest, disputed or scenario.

`TemporalExtent` supports closed or open-ended intervals. Calendar-year queries use interval overlap: requesting 2026 returns any feature whose validity intersects 1 January through 31 December 2026, not only features active on 1 January.

Navigation bands are Deep Time/Prehistory, Ancient World, Medieval/Early Modern, Industrial/Modern, Digital Era, Near Future and Far Future. These are UI/indexing bands, not claims that historical eras begin globally on the same date.

## Truth modes

- `fact`: evidence-bound verified state; future facts on canonical reality are forbidden.
- `claim`: sourced assertion not promoted to fact.
- `belief`: analyst/model assessment with confidence.
- `reconstruction`: evidence-supported historical reconstruction without false modern precision.
- `planned`: sourced announced/approved future state, not a prediction of completion.
- `scenario`: counterfactual state available only on a World Fork.

## Realms

- `physical`: real-world geography through time.
- `historical_reconstruction`: scholarly/archaeological spatial interpretations.
- `digital_twin`: structured digital representations of physical places/objects.
- `mixed_reality`: virtual content spatially anchored to physical reality.
- `metaverse`: independent or Earth-anchored virtual worlds.
- `simulation`: generated/counterfactual environments.

## Coordinate spaces

Every feature points to a `CoordinateSpace` rather than assuming latitude/longitude. Supported kinds are `earth_geodetic`, `earth_projected`, `indoor_local`, `digital_twin`, `mixed_reality`, `virtual_world`, `simulation` and `celestial`.

A coordinate space can contain a stable space ID, CRS, parent space, platform, scene URI, GeoPose-style Earth anchor, local origin, local-axis convention and metadata. Therefore `[10, 2, -4]` in a metaverse scene remains local coordinates; the scene itself can optionally be anchored to Earth.

## Cross-realm portals

`PortalReference` connects spaces without pretending they share the same coordinate system. A portal stores target space, optional target feature, directionality, optional 4x4 transform and metadata.

Examples include physical museum -> digital-twin interior, İzmir square -> mixed-reality overlay, physical venue -> metaverse event hall, virtual world -> virtual world and a canonical place -> scenario representation.

## Geometry and spatial indexing

Earth features support GeoJSON Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon and GeometryCollection. Bounding boxes are derived for spatial filters. Virtual/local spaces use 3D local positions and scene metadata.

Queries filter by branch, calendar year, realm, feature type, bounding box, source ID and limit.

## Ultra-detailed layer taxonomy

### Natural Earth/environment

Continents, terrain/elevation, bathymetry, coastlines by period, rivers/lakes/wetlands, glaciers, geology, soils, vegetation, habitats/protected areas, climate zones, weather observations, natural hazards, earthquakes, volcanoes, wildfire/flood extents.

### Political/administrative

Historical polities and empires, countries, disputed territories, provinces/states, municipalities, neighborhoods, electoral/jurisdiction boundaries, maritime zones and boundary-change events. Every boundary may have its own temporal validity and uncertainty.

### Human settlement

Archaeological sites, ancient settlements, cities, villages, neighborhoods, parcels where licensing permits, addresses, buildings, interiors, landmarks, public spaces, cemeteries, religious sites, schools, hospitals and government facilities.

### Transportation

Ancient routes, roads/highways, rail, tram/metro, maritime routes, ports, airports/runways, cycling/pedestrian networks, bridges/tunnels, stops, traffic observations and planned infrastructure.

### Utilities/critical infrastructure

Power generation/grids, water/wastewater, pipelines, telecommunications, data centers, public satellite/ground-station context, logistics and emergency infrastructure. Sensitive/restricted data remains subject to access policy.

### Economy/organizations

Companies/facilities, supply-chain nodes, markets, commercial districts, projects, sourced public tenders, extraction, agriculture, energy assets and economic events connected to places.

### Culture/history

Monuments, museums, historical events, battles, migrations, historical routes, language/cultural regions, place names through time, historical imagery footprints and source documents connected to places.

### Science/observation

Research institutions, observatories, field stations, scientific observations, scholarly claims linked to locations, sensor stations, IoT observations and remote-sensing asset footprints.

### Digital layer

Web platforms associated with entities, public service/network regions, digital assets, software/services, knowledge-graph entities and online events. Personal/sensitive digital identities require explicit privacy/authorization policy.

### Digital twin/3D

Semantic city objects, BIM/CAD references, point clouds, photogrammetry, 3D buildings, terrain meshes, 3D Tiles, CityGML semantics, live sensors, simulation states and maintenance/status metadata.

### Mixed reality

Anchored annotations, AR experiences, persistent spatial content, local anchors, physical-to-digital portals and event overlays.

### Metaverse

Worlds, regions, platform-defined parcels, scene roots, buildings/objects, portal graph, event spaces, virtual transport and persistent assets. Avatar storage/use remains privacy- and authorization-bound. Virtual economic/token objects remain separate evidence-bound entities rather than assumed values.

### Future/scenario

Official plans, approved-but-unbuilt infrastructure, scheduled events, forecasts, model-generated scenarios, World Fork alternatives, scenario confidence, causal assumptions and outcome deltas versus reality.

## 3D and interoperability

OSIRIS references multiple open standards rather than forcing one format:

- CityGML: semantic 3D city/digital-twin model.
- 3D Tiles: massive geospatial 3D streaming.
- GeoPose: location/orientation of real or virtual objects in explicit reference frames.
- glTF: efficient runtime 3D asset delivery.
- OpenUSD: composable scene description/data interchange for complex 3D worlds, twins and simulation.
- STAC: spatiotemporal asset catalog references.
- GeoSPARQL: semantic spatial relationships.
- OGC API Features/Tiles: interoperable feature/tile access patterns.
- SensorThings: live geospatial observations.

`AssetReference` records URI, format, media type, level of detail, checksum, source ID and metadata.

## Historical source strategy

Pleiades supplies ancient places/locations/names/connections; identifiers and attribution are preserved. OpenHistoricalMap supplies historical changes to human/natural geography. Wikidata supplies linked identifiers and date precision/qualifiers such as earliest/latest/circa/disputed. Conflicting historical sources remain competing sourced reconstructions rather than being flattened into fabricated certainty.

## Present/live source strategy

OpenStreetMap and configured geospatial providers supply present context under applicable licenses. GDELT can supply near-real-time event/news signals. OpenAlex/Crossref supply scholarly signals. SensorThings-compatible services can provide physical observations.

Provider information must first pass OSIRIS evidence/provenance processing. Sensor Mesh does not promote raw model memory into world truth.

## World Sensor Mesh

Pipeline:

1. provider federation collects read-only evidence;
2. OSIRIS assigns evidence IDs/provenance digests;
3. unsupported claims are removed by evidence sanitization;
4. a stable sensor digest deduplicates repeated results;
5. supported findings enter OSIRIS World as `claim` or `belief`;
6. geospatial markers enter Temporal Reality Atlas;
7. watchlists repeat the process on schedule;
8. sensor receipts record ingestion/dedup status.

Normal investigations, streaming investigations and recurring watchlists now use this path. Sensor Mesh never automatically turns model output into a `fact`.

## World Fork integration

Atlas queries follow branch lineage. A fork inherits parent geography and overlays only its own scenario features. Canonical reality never inherits a child scenario.

Example: Reality contains current İzmir. Fork A contains a 2040 adaptation project completed; Fork B contains no adaptation; Fork C contains a different transport plan. All three share past/current evidence but keep future geometries separate.

## API

Atlas:

- `GET /world/atlas`
- `GET /world/atlas/standards`
- `GET /world/atlas/sources`
- `GET /world/atlas/layers`
- `POST /world/atlas/features`
- `POST /world/atlas/features/batch`
- `GET /world/atlas/features`
- `GET /world/atlas/timeline`
- `GET /world/atlas/portals`

Sensor Mesh:

- `GET /world/sensors`
- `GET /world/sensors/sources`
- `GET /world/sensors/receipts`

## Implemented vs data-dependent

Implemented: BCE-to-future time model, uncertainty, truth rules, physical/reconstruction/twin/MR/metaverse/simulation realms, explicit coordinate spaces, GeoPose-style anchors, GeoJSON, local 3D positions, 3D asset references, portals, tenant isolation, temporal/spatial/source filters, fork-aware queries, timeline aggregation, Sensor Mesh ingestion, automatic investigation/watchlist ingestion, dedup receipts and regression tests.

Not claimed as preloaded: all human history, every Pleiades/OHM/Wikidata record, all OSM, every private/commercial digital twin, every metaverse platform or exact future geography. Those remain source-adapter, import, authorization and licensing work. The architecture deliberately keeps source acquisition separate from reality semantics.

## Safety/privacy/commercial rules

External provider access stays read-only. The Atlas does not introduce active scanning, exploitation, credential collection or intrusive tracking. Sensitive personal location data is not promoted into shared layers without authorized policy. Provider licensing/attribution obligations remain attached to source metadata.
