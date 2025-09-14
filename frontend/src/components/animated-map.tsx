'use client';

import { useEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import type { Map } from 'leaflet';
type LeafletModule = typeof import('leaflet');

export function AnimatedMap() {
  const { resolvedTheme } = useTheme();
  const [isMounted, setIsMounted] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const tileLayerRef = useRef<ReturnType<LeafletModule['tileLayer']> | null>(null);
  const LRef = useRef<LeafletModule | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    let canceled = false;
    (async () => {
      if (typeof window === 'undefined' || !isMounted) return;
      const imported = (await import('leaflet')) as unknown as {
        default?: LeafletModule;
      } & LeafletModule;
      const L: LeafletModule = imported.default ?? (imported as LeafletModule);
      LRef.current = L;

      if (canceled || !containerRef.current) return;
      if (mapRef.current) return;

      const map = L.map(containerRef.current, {
        zoomControl: false,
        attributionControl: false,
        worldCopyJump: true,
        dragging: false,
        touchZoom: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        boxZoom: false,
        keyboard: false,
      }).setView([20, 0], 2);

      mapRef.current = map;

      const theme =
        resolvedTheme ?? (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
      const url =
        theme === 'dark'
          ? 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png'
          : 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png';
      tileLayerRef.current = L.tileLayer(url, { maxZoom: 15, keepBuffer: 5 }).addTo(map);

      try {
        const tilePane = map.getPanes().tilePane;
        if (tilePane) {
          tilePane.style.filter =
            theme === 'dark' ? 'grayscale(1) brightness(0.8)' : 'grayscale(1)';
        }
      } catch {}

      const places: Array<{ name: string; lat: number; lng: number; zoom: number }> = [
        { name: 'MIT', lat: 42.360091, lng: -71.09416, zoom: 7 },
        { name: 'Stanford', lat: 37.4275, lng: -122.1697, zoom: 7 },
        { name: 'Caltech', lat: 34.1377, lng: -118.1253, zoom: 7 },
        { name: 'ETH Zürich', lat: 47.3763, lng: 8.5476, zoom: 7 },
        { name: 'CERN', lat: 46.233, lng: 6.053, zoom: 7 },
        { name: 'Cambridge', lat: 52.2043, lng: 0.1149, zoom: 7 },
        { name: 'Oxford', lat: 51.7548, lng: -1.2544, zoom: 7 },
        { name: 'The University of Tokyo', lat: 35.7126, lng: 139.761, zoom: 7 },
        { name: 'Tsinghua University', lat: 40.0025, lng: 116.3269, zoom: 7 },
      ];

      let i = 0;
      const step = () => {
        const p = places[i % places.length];
        map.flyTo([p.lat, p.lng], p.zoom, {
          duration: 1.6,
          easeLinearity: 1,
          noMoveStart: true,
        });
        i += 1;
      };

      step();
      timerRef.current = setInterval(step, 3500);
    })();

    return () => {
      canceled = true;
      if (timerRef.current) clearInterval(timerRef.current);
      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch {}
        mapRef.current = null;
      }
      tileLayerRef.current = null;
      LRef.current = null;
    };
  }, [isMounted, resolvedTheme]);

  useEffect(() => {
    const map = mapRef.current;
    const L = LRef.current;
    if (!map || !L) return;
    const url =
      resolvedTheme === 'dark'
        ? 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png'
        : 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png';
    if (tileLayerRef.current) {
      try {
        map.removeLayer(tileLayerRef.current);
      } catch {}
      tileLayerRef.current = null;
    }
    tileLayerRef.current = L.tileLayer(url, { maxZoom: 15, keepBuffer: 5 }).addTo(map);
    try {
      const tilePane = map.getPanes().tilePane;
      if (tilePane) {
        tilePane.style.filter =
          resolvedTheme === 'dark' ? 'grayscale(1) brightness(0.8)' : 'grayscale(1)';
      }
    } catch {}
  }, [resolvedTheme]);
  if (!isMounted) {
    return (
      <div className="absolute inset-0">
        <div className="pointer-events-none h-full w-full overflow-hidden select-none bg-muted/20" />
      </div>
    );
  }

  return (
    <div className="absolute inset-0">
      <div
        ref={containerRef}
        aria-label="Animated map"
        className="pointer-events-none h-full w-full overflow-hidden select-none"
      />
    </div>
  );
}
