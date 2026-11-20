import { StyleSheet, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { Txt } from '@/components/finexa-ui';
import { C } from '@/constants/theme';
import type { Point } from '@/work-tracking';

const CAIRO: Point = { lat: 30.0444, lon: 31.2357 }; // where the map starts when nothing is known yet

export function WorkMap({
  workplace,
  radius,
  you,
  onPick,
}: {
  workplace: Point | null;
  radius: number;
  you: Point | null;
  onPick?: (p: Point) => void; // sign-up: tap the map to place the workplace (people sign up at home, not at work)
}) {
  const center = workplace ?? you ?? (onPick ? CAIRO : null);
  if (!center) {
    return (
      <View style={[s.map, s.empty]}>
        <Txt style={s.emptyText}>Set your workplace to see it on the map.</Txt>
      </View>
    );
  }
  const data = JSON.stringify({ center, workplace, radius, you, pick: !!onPick, indigo: C.indigo, green: C.green });
  const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html, body, #map { height: 100%; margin: 0; background: ${C.surface}; }</style></head>
<body><div id="map"></div><script>
var d = ${data};
var map = L.map('map', { zoomControl: false }).setView([d.center.lat, d.center.lon], 16);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
var shown = [];
if (d.workplace) shown.push(L.circle([d.workplace.lat, d.workplace.lon],
  { radius: d.radius, color: d.indigo, weight: 2, fillOpacity: 0.15 }).addTo(map));
if (d.you) shown.push(L.circleMarker([d.you.lat, d.you.lon],
  { radius: 7, color: '#fff', weight: 2, fillColor: d.green, fillOpacity: 1 }).addTo(map));
if (shown.length) map.fitBounds(L.featureGroup(shown).getBounds().pad(0.25), { maxZoom: 17 });
else map.setZoom(12);
if (d.pick) map.on('click', function (e) {
  window.ReactNativeWebView.postMessage(JSON.stringify({ lat: e.latlng.lat, lon: e.latlng.lng }));
});
</script></body></html>`;
  return (
    <View style={[s.map, onPick && { height: 280 }]}>
      <WebView
        originWhitelist={['*']}
        source={{ html }}
        onMessage={(e) => onPick?.(JSON.parse(e.nativeEvent.data))}
        applicationNameForUserAgent="Finexa-demo"
        scrollEnabled={false}
        style={{ backgroundColor: C.surface }}
      />
    </View>
  );
}

const s = StyleSheet.create({
  map: { height: 220, borderRadius: 12, overflow: 'hidden', borderColor: C.line, borderWidth: 1 },
  empty: { alignItems: 'center', justifyContent: 'center', padding: 16 },
  emptyText: { color: C.muted, fontSize: 13, textAlign: 'center' },
});
