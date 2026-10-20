import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

// Sequential blue ramp (dataviz skill reference palette, steps 100->700):
// low storage % is light, high storage % is dark - a magnitude encoding, not
// a status/threshold judgement (SEQ's actual drought-trigger percentages
// aren't confirmed yet - see docs/decisions.md - so this deliberately doesn't
// imply "red = bad" without a verified threshold to base it on).
const FILL_COLOR = [
  "interpolate",
  ["linear"],
  ["coalesce", ["get", "latest_pct"], 0],
  0,
  "#cde2fb",
  25,
  "#9ec5f4",
  50,
  "#5598e7",
  75,
  "#2a78d6",
  100,
  "#104281",
];

export default function MapView({ dams, selectedDam, onSelectDam }) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const boundsFitRef = useRef(false);
  const skippedFirstZoomRef = useRef(false);
  // Holds the real extent of every dam, set once dams load - kept separate
  // from boundsFitRef (which only guards the automatic first-load fit) so
  // the "fit all" button can re-run the same fit at any time afterward,
  // including after the user has zoomed into one selected dam.
  const allDamsBoundsRef = useRef(null);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      center: [152.9, -27.4],
      zoom: 7.2,
    });
    mapRef.current = map;
    popupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(
      new FitAllControl(() => {
        if (allDamsBoundsRef.current) {
          map.fitBounds(allDamsBoundsRef.current, { padding: 32, duration: 500 });
        }
      }),
      "top-right",
    );

    map.on("load", () => {
      map.addSource("dams", { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      map.addLayer({
        id: "dams-fill",
        type: "fill",
        source: "dams",
        paint: {
          "fill-color": FILL_COLOR,
          "fill-opacity": [
            "case",
            ["==", ["get", "dam_name"], ["literal", ""]],
            0.9,
            0.75,
          ],
        },
      });

      map.addLayer({
        id: "dams-outline",
        type: "line",
        source: "dams",
        paint: {
          "line-color": "#0b0b0b",
          "line-width": ["case", ["get", "isSelected"], 3, 1],
          "line-opacity": ["case", ["get", "isSelected"], 1, 0.4],
        },
      });

      map.on("mousemove", "dams-fill", (e) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = e.features?.[0];
        if (!feature) return;
        const { dam_name: damName, latest_pct: pct, latest_volume_ml: volumeMl } = feature.properties;
        const pctText = pct != null ? `${Number(pct).toFixed(1)}%` : "no data";
        const volText = volumeMl != null ? `${Math.round(Number(volumeMl)).toLocaleString()} ML` : "";
        popupRef.current
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${escapeHtml(damName)}</strong><br/>${escapeHtml(pctText)} full${volText ? ` &middot; ${escapeHtml(volText)}` : ""}`,
          )
          .addTo(map);
      });

      map.on("mouseleave", "dams-fill", () => {
        map.getCanvas().style.cursor = "";
        popupRef.current.remove();
      });

      map.on("click", "dams-fill", (e) => {
        const feature = e.features?.[0];
        if (feature) onSelectDam(feature.properties.dam_name);
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !dams) return;
    const withSelection = {
      ...dams,
      features: dams.features.map((f) => ({
        ...f,
        properties: { ...f.properties, isSelected: f.properties.dam_name === selectedDam },
      })),
    };
    const setData = () => map.getSource("dams")?.setData(withSelection);
    if (map.isStyleLoaded()) setData();
    else map.once("load", setData);

    // Fit to the real dam extent once, instead of a guessed center/zoom - a
    // fixed whole-SEQ view made the actual reservoir polygons (much smaller
    // footprint than the region) look like tiny specks, confirmed live.
    if (!allDamsBoundsRef.current && dams.features.length) {
      const bounds = new maplibregl.LngLatBounds();
      for (const feature of dams.features) {
        forEachCoordinate(feature.geometry, (lng, lat) => bounds.extend([lng, lat]));
      }
      allDamsBoundsRef.current = bounds;
    }
    if (!boundsFitRef.current && allDamsBoundsRef.current) {
      boundsFitRef.current = true;
      const fit = () => map.fitBounds(allDamsBoundsRef.current, { padding: 32, duration: 0 });
      if (map.isStyleLoaded()) fit();
      else map.once("load", fit);
    }
  }, [dams, selectedDam]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !dams || !selectedDam) return;
    // Skip the very first run (the default-selected dam on mount) so the
    // user sees the whole-region overview first, not an immediate zoom past
    // it - the ref flips true in the same effect-flush pass as the
    // overview-fit effect above (both depend on [dams, selectedDam]).
    if (!skippedFirstZoomRef.current) {
      skippedFirstZoomRef.current = true;
      return;
    }

    const feature = dams.features.find((f) => f.properties.dam_name === selectedDam);
    if (!feature) return;
    const bounds = new maplibregl.LngLatBounds();
    forEachCoordinate(feature.geometry, (lng, lat) => bounds.extend([lng, lat]));
    // No isStyleLoaded()/once("load") gate here, unlike the add-source/
    // add-layer setup above (which genuinely needs the style loaded) - a
    // camera move doesn't. Confirmed live that gate was the actual bug:
    // map.isStyleLoaded() returned false on a long-since-fully-loaded,
    // already-interactive map (an unrelated internal state, not "hasn't
    // loaded yet"), silently routing into a once("load", ...) listener that
    // can never fire again since "load" only ever fires once per map
    // instance - the zoom silently never happened.
    map.fitBounds(bounds, {
      padding: 80,
      maxZoom: 13, // some reservoirs (e.g. Lake Macdonald) are tiny - caps how tight this zooms
      duration: 800,
    });
  }, [selectedDam, dams]);

  return <div ref={mapContainerRef} className="map-view" />;
}

// A plain MapLibre IControl (onAdd/onRemove) rather than a React-rendered
// overlay - it needs to live inside MapLibre's own "top-right" control
// stack (same corner as the +/- zoom buttons, directly below them) so it
// reads as one more map tool, not a separate floating element.
class FitAllControl {
  constructor(onClick) {
    this._onClick = onClick;
  }

  onAdd() {
    this._container = document.createElement("div");
    this._container.className = "maplibregl-ctrl maplibregl-ctrl-group";
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", "Reset to default view (all dams)");
    button.title = "Reset to default view (all dams)";
    // A house icon, not corner brackets - the latter reads as "fullscreen"
    // (an unrelated browser affordance), where a home glyph is the
    // established "reset view" convention in map UIs.
    button.innerHTML =
      '<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3.5 10.5L10 4l6.5 6.5M5.5 8.75V16a.5.5 0 0 0 .5.5h3v-4h2v4h3a.5.5 0 0 0 .5-.5V8.75" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    button.addEventListener("click", () => this._onClick());
    this._container.appendChild(button);
    return this._container;
  }

  onRemove() {
    this._container.parentNode?.removeChild(this._container);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Walks a GeoJSON geometry's coordinate arrays regardless of nesting depth
// (Polygon vs MultiPolygon), calling `fn(lng, lat)` for every vertex.
function forEachCoordinate(geometry, fn) {
  const walk = (coords) => {
    if (typeof coords[0] === "number") {
      fn(coords[0], coords[1]);
    } else {
      for (const c of coords) walk(c);
    }
  };
  walk(geometry.coordinates);
}
