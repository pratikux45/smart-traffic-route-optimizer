/**
 * Smart Traffic Route Optimizer - Frontend Client Application
 * Modular, clean, Google Maps-style navigation dashboard.
 */

document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // State Management
    // ==========================================
    let map = null;
    let startLocation = null;       // { latitude, longitude, display_name }
    let destLocation = null;        // { latitude, longitude, display_name }

    let activeRoutesData = [];      // Array of route objects from backend
    let optimizedRouteId = null;    // ID of the optimized route (e.g. "route_1")
    let selectedRouteId = null;     // ID of currently selected route
    let hoveredRouteId = null;      // ID of route currently hovered by mouse
    let areSignalsVisible = true;   // Traffic signal visibility toggle state

    // Leaflet Dedicated Layer Groups
    let sourceLayerGroup = null;
    let destinationLayerGroup = null;
    let alternativeRouteGroup = null;
    let optimizedRouteGroup = null;
    let signalLayerGroup = null;

    // Cache of route polyline layers keyed by route_id
    const routeLayersMap = {};

    // ==========================================
    // DOM Element References
    // ==========================================
    const startInput = document.getElementById('startInput');
    const destInput = document.getElementById('destInput');
    const startSuggestions = document.getElementById('startSuggestions');
    const destSuggestions = document.getElementById('destSuggestions');
    const clearStartBtn = document.getElementById('clearStartBtn');
    const clearDestBtn = document.getElementById('clearDestBtn');
    const swapBtn = document.getElementById('swapLocationsBtn');
    const findRoutesBtn = document.getElementById('findRoutesBtn');
    const routesContainer = document.getElementById('routesContainer');
    const alertContainer = document.getElementById('alertContainer');
    const mapStatusOverlay = document.getElementById('mapStatusOverlay');
    const mapStatusText = document.getElementById('mapStatusText');
    const mapLegend = document.getElementById('mapLegend');
    const comparisonContainer = document.getElementById('comparisonContainer');
    const comparisonTableBody = document.getElementById('comparisonTableBody');
    const toggleSignalsCheckbox = document.getElementById('toggleSignalsCheckbox');
    const signalCountBadge = document.getElementById('signalCountBadge');
    const fitBoundsBtn = document.getElementById('fitBoundsBtn');

    // ==========================================
    // 1. Initialize Map & Layer Groups
    // ==========================================
    function initializeMap() {
        // Default center: India (20.5937, 78.9629), Zoom 5
        map = L.map('map', {
            zoomControl: true,
            attributionControl: true
        }).setView([20.5937, 78.9629], 5);

        // OpenStreetMap Standard Tile Layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'
        }).addTo(map);

        // Initialize separate layer groups to manage visual hierarchy
        alternativeRouteGroup = L.layerGroup().addTo(map);
        optimizedRouteGroup = L.layerGroup().addTo(map);
        signalLayerGroup = L.layerGroup().addTo(map);
        sourceLayerGroup = L.layerGroup().addTo(map);
        destinationLayerGroup = L.layerGroup().addTo(map);

        // Map Click: allow user to click on map to set start or destination
        map.on('click', (e) => {
            const lat = parseFloat(e.latlng.lat.toFixed(5));
            const lon = parseFloat(e.latlng.lng.toFixed(5));
            const coordsText = `${lat}, ${lon}`;

            if (!startLocation) {
                startLocation = { latitude: lat, longitude: lon, display_name: `Point (${coordsText})` };
                startInput.value = coordsText;
                clearStartBtn.style.display = 'block';
                renderEndpointMarkers();
            } else if (!destLocation) {
                destLocation = { latitude: lat, longitude: lon, display_name: `Point (${coordsText})` };
                destInput.value = coordsText;
                clearDestBtn.style.display = 'block';
                renderEndpointMarkers();
            }
        });
    }

    // ==========================================
    // 2. Autocomplete & Geocoding
    // ==========================================
    function debounce(func, delay = 350) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => func.apply(this, args), delay);
        };
    }

    function setupSearch() {
        setupAutocomplete(startInput, startSuggestions, clearStartBtn, (loc) => {
            startLocation = loc;
            renderEndpointMarkers();
        });

        setupAutocomplete(destInput, destSuggestions, clearDestBtn, (loc) => {
            destLocation = loc;
            renderEndpointMarkers();
        });

        // Swap locations
        swapBtn.addEventListener('click', () => {
            const tempText = startInput.value;
            const tempLoc = startLocation;

            startInput.value = destInput.value;
            startLocation = destLocation;

            destInput.value = tempText;
            destLocation = tempLoc;

            clearStartBtn.style.display = startInput.value ? 'block' : 'none';
            clearDestBtn.style.display = destInput.value ? 'block' : 'none';

            renderEndpointMarkers();
            if (startLocation && destLocation && activeRoutesData.length > 0) {
                calculateRoutes();
            }
        });

        // Toggle Signals Control
        toggleSignalsCheckbox.addEventListener('change', (e) => {
            toggleSignals(e.target.checked);
        });

        // Fit Bounds Button
        fitBoundsBtn.addEventListener('click', () => {
            fitRoutesToBounds();
        });

        // Find Routes Action
        findRoutesBtn.addEventListener('click', () => {
            calculateRoutes();
        });

        // Quick Demo Preset Chip
        const demoNagpurBtn = document.getElementById('demoNagpurBtn');
        if (demoNagpurBtn) {
            demoNagpurBtn.addEventListener('click', () => {
                startInput.value = "Nagpur Railway Station";
                startLocation = {
                    latitude: 21.1524,
                    longitude: 79.0888,
                    display_name: "Nagpur Railway Station, Maharashtra, India"
                };
                clearStartBtn.style.display = 'block';

                destInput.value = "Futala Lake, Nagpur";
                destLocation = {
                    latitude: 21.1558,
                    longitude: 79.0442,
                    display_name: "Futala Lake, Nagpur, Maharashtra, India"
                };
                clearDestBtn.style.display = 'block';

                renderEndpointMarkers();
                calculateRoutes();
            });
        }
    }

    function setupAutocomplete(inputEl, dropdownEl, clearBtn, setLocationCallback) {
        inputEl.addEventListener('input', debounce(async () => {
            const query = inputEl.value.trim();
            if (query.length > 0) {
                clearBtn.style.display = 'block';
            } else {
                clearBtn.style.display = 'none';
                dropdownEl.style.display = 'none';
                setLocationCallback(null);
                return;
            }

            if (query.length < 2) return;

            try {
                const results = await geocodeLocation(query);
                renderSuggestions(results, dropdownEl, inputEl, setLocationCallback);
            } catch (err) {
                console.error("Geocoding fetch error:", err);
            }
        }, 350));

        clearBtn.addEventListener('click', () => {
            inputEl.value = '';
            clearBtn.style.display = 'none';
            dropdownEl.style.display = 'none';
            setLocationCallback(null);
            renderEndpointMarkers();
        });
    }

    async function geocodeLocation(query) {
        if (!query) return [];
        const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
        if (!res.ok) return [];
        const data = await res.json();
        return data.results || [];
    }

    function renderSuggestions(results, dropdownEl, inputEl, setLocationCallback) {
        dropdownEl.innerHTML = '';
        if (!results || results.length === 0) {
            dropdownEl.style.display = 'none';
            return;
        }

        results.forEach(item => {
            const div = document.createElement('div');
            div.className = 'suggestion-item';
            div.innerHTML = `<i class="fa-solid fa-location-dot text-subtle"></i> <span>${escapeHtml(item.display_name)}</span>`;

            div.addEventListener('click', () => {
                inputEl.value = item.display_name;
                setLocationCallback({
                    latitude: item.latitude,
                    longitude: item.longitude,
                    display_name: item.display_name
                });
                dropdownEl.style.display = 'none';
            });

            dropdownEl.appendChild(div);
        });

        dropdownEl.style.display = 'block';
    }

    // Dismiss suggestion dropdowns on click outside
    document.addEventListener('click', (e) => {
        if (!startInput.contains(e.target) && !startSuggestions.contains(e.target)) {
            startSuggestions.style.display = 'none';
        }
        if (!destInput.contains(e.target) && !destSuggestions.contains(e.target)) {
            destSuggestions.style.display = 'none';
        }
    });

    async function resolveLocation(query) {
        if (!query) return null;
        try {
            const results = await geocodeLocation(query);
            if (results && results.length > 0) {
                return {
                    latitude: results[0].latitude,
                    longitude: results[0].longitude,
                    display_name: results[0].display_name
                };
            }
        } catch (err) {
            console.error("Error resolving location:", err);
        }
        return null;
    }

    // ==========================================
    // 3. Endpoint Markers (Start & Destination)
    // ==========================================
    function renderEndpointMarkers() {
        sourceLayerGroup.clearLayers();
        destinationLayerGroup.clearLayers();

        if (startLocation) {
            const startIcon = L.divIcon({
                className: 'custom-pin-icon',
                html: `<div class="custom-pin pin-green" title="Origin"><i class="fa-solid fa-location-dot"></i></div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 30]
            });
            L.marker([startLocation.latitude, startLocation.longitude], { icon: startIcon })
                .bindPopup(`<b>Origin:</b><br>${escapeHtml(startLocation.display_name)}`)
                .addTo(sourceLayerGroup);
        }

        if (destLocation) {
            const destIcon = L.divIcon({
                className: 'custom-pin-icon',
                html: `<div class="custom-pin pin-red" title="Destination"><i class="fa-solid fa-flag-checkered"></i></div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 30]
            });
            L.marker([destLocation.latitude, destLocation.longitude], { icon: destIcon })
                .bindPopup(`<b>Destination:</b><br>${escapeHtml(destLocation.display_name)}`)
                .addTo(destinationLayerGroup);
        }
    }

    // ==========================================
    // 4. Calculate Routes
    // ==========================================
    async function calculateRoutes() {
        clearAlerts();

        const startText = startInput.value.trim();
        const destText = destInput.value.trim();

        if (!startText || !destText) {
            showAlert("Please enter both an origin and destination location.", "warning");
            return;
        }

        setLoadingState(true, "Resolving locations...");

        if (!startLocation) {
            startLocation = await resolveLocation(startText);
        }
        if (!destLocation) {
            destLocation = await resolveLocation(destText);
        }

        if (!startLocation || !destLocation) {
            setLoadingState(false);
            showAlert("Unable to resolve coordinates for the entered locations. Please try a more specific search.", "error");
            return;
        }

        renderEndpointMarkers();

        // Get selected optimization priority
        const selectedPref = document.querySelector('input[name="routePreference"]:checked')?.value || "balanced";

        setLoadingState(true, "Finding driving routes & analyzing traffic signals...");

        try {
            const response = await fetch('/api/routes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start: { latitude: startLocation.latitude, longitude: startLocation.longitude },
                    destination: { latitude: destLocation.latitude, longitude: destLocation.longitude },
                    start_label: startLocation.display_name,
                    destination_label: destLocation.display_name,
                    preference: selectedPref
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Unable to calculate routes right now. Please try again.");
            }

            if (data.warning) {
                showAlert(data.warning, "warning");
            }

            activeRoutesData = data.routes || [];
            optimizedRouteId = data.optimization?.optimized_route_id || data.optimized_route_id;
            selectedRouteId = optimizedRouteId; // Default selection is optimized route

            renderRoutes(activeRoutesData);
            updateRouteCards(activeRoutesData);
            renderRouteComparisonTable(activeRoutesData);

            if (activeRoutesData.length > 0) {
                mapLegend.style.display = 'block';
                comparisonContainer.style.display = 'block';
                fitBoundsBtn.style.display = 'inline-flex';
                fitRoutesToBounds();
            }

        } catch (err) {
            console.error("Route calculation error:", err);
            showAlert(err.message || "Unable to calculate routes right now. Please try again.", "error");
        } finally {
            setLoadingState(false);
        }
    }

    // ==========================================
    // 5. Render Routes & Visual Hierarchy
    // ==========================================
    function renderRoutes(routes) {
        clearRoutes();

        if (!routes || routes.length === 0) return;

        // Render alternative routes first, then optimized route on top
        routes.forEach(route => {
            renderRoute(route);
        });

        // Render traffic signals for the selected route
        renderSignalsForSelectedRoute();

        // Apply visual styling hierarchy
        updateRouteStyles();
    }

    function renderRoute(route) {
        const rId = route.route_id || `route_${route.id}`;
        const isOpt = (rId === optimizedRouteId);

        const targetLayerGroup = isOpt ? optimizedRouteGroup : alternativeRouteGroup;

        const polyline = L.geoJSON(route.geometry, {
            style: {
                color: isOpt ? '#10b981' : '#64748b',
                weight: isOpt ? 7 : 5,
                opacity: isOpt ? 0.9 : 0.5
            }
        }).addTo(targetLayerGroup);

        // Interactive hover tooltip
        polyline.bindTooltip(
            `<strong>${escapeHtml(route.name)}</strong><br>` +
            `${route.distance_km} km • ${route.duration_min} min drive<br>` +
            `Signals: ${route.signal_count} (~${route.estimated_signal_delay_min} min delay)<br>` +
            `Optimization Score: ${route.scores ? route.scores.total : route.optimization_score}`,
            { sticky: true, className: 'route-tooltip' }
        );

        // Click to select route
        polyline.on('click', () => {
            selectRoute(rId);
        });

        // Mouse hover effects
        polyline.on('mouseover', () => {
            hoveredRouteId = rId;
            updateRouteStyles();
        });

        polyline.on('mouseout', () => {
            hoveredRouteId = null;
            updateRouteStyles();
        });

        routeLayersMap[rId] = polyline;
    }

    // ==========================================
    // 6. Update Route Styling Engine
    // ==========================================
    function updateRouteStyles() {
        Object.keys(routeLayersMap).forEach(rId => {
            const layer = routeLayersMap[rId];
            if (!layer) return;

            const isOptimized = (rId === optimizedRouteId);
            const isSelected = (rId === selectedRouteId);
            const isHovered = (rId === hoveredRouteId);

            let color = '#64748b'; // Muted slate for alternative routes
            let weight = 5;
            let opacity = 0.55;
            let dashArray = null;

            if (isSelected) {
                if (isOptimized) {
                    color = '#10b981'; // Vibrant emerald for optimized route
                    weight = 9;
                    opacity = 1.0;
                } else {
                    color = '#38bdf8'; // Sky blue for selected alternative
                    weight = 8;
                    opacity = 0.95;
                }
            } else if (isOptimized) {
                // Optimized route when another is selected remains prominent and distinct
                color = '#10b981';
                weight = 6;
                opacity = 0.85;
            }

            if (isHovered && !isSelected) {
                weight += 2;
                opacity = Math.min(1.0, opacity + 0.3);
            }

            layer.setStyle({
                color: color,
                weight: weight,
                opacity: opacity,
                dashArray: dashArray,
                lineCap: 'round',
                lineJoin: 'round'
            });

            // Ensure selected or optimized route layers sit on top
            if (isSelected) {
                layer.bringToFront();
            }
        });
    }

    // ==========================================
    // 7. Traffic Signal Rendering & Route Association
    // ==========================================
    function renderSignalsForSelectedRoute() {
        signalLayerGroup.clearLayers();

        if (!areSignalsVisible || !selectedRouteId) {
            signalCountBadge.style.display = 'none';
            return;
        }

        const selectedRoute = activeRoutesData.find(
            r => (r.route_id === selectedRouteId || `route_${r.id}` === selectedRouteId)
        );

        if (!selectedRoute) return;

        const signals = selectedRoute.signals || selectedRoute.traffic_signals || [];
        signalCountBadge.textContent = signals.length;
        signalCountBadge.style.display = signals.length > 0 ? 'inline-block' : 'none';

        // Keep track of coordinates to slightly offset overlapping markers at identical locations
        const seenCoords = new Map();

        signals.forEach(sig => {
            const coordKey = `${sig.latitude.toFixed(5)},${sig.longitude.toFixed(5)}`;
            const count = seenCoords.get(coordKey) || 0;
            seenCoords.set(coordKey, count + 1);

            let renderLat = sig.latitude;
            let renderLon = sig.longitude;

            if (count > 0) {
                // Apply slight geographic offset (~3-5m) in a radial pattern so both markers remain visible
                const angle = count * 1.25;
                const offsetDist = count * 0.00004;
                renderLat += offsetDist * Math.sin(angle);
                renderLon += offsetDist * Math.cos(angle);
            }

            const marker = createSignalMarker({ ...sig, latitude: renderLat, longitude: renderLon }, selectedRoute.name);
            marker.addTo(signalLayerGroup);
        });
    }

    function createSignalMarker(sig, routeName) {
        const signalIcon = L.divIcon({
            className: 'signal-icon-wrapper',
            html: `<div class="signal-icon-marker" title="Traffic Signal - ${escapeHtml(routeName)}"><i class="fa-solid fa-traffic-light"></i></div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13]
        });

        const kmFromStart = (sig.distance_along_route_m / 1000.0).toFixed(2);
        const osmIdText = sig.id ? `<div class="popup-meta-row"><span>OSM ID:</span> <code>${escapeHtml(sig.id)}</code></div>` : '';
        const nameText = sig.name ? `<div class="popup-meta-row"><span>Intersection:</span> <strong>${escapeHtml(sig.name)}</strong></div>` : '';

        const popupHtml = `
            <div class="signal-popup-card">
                <div class="signal-popup-header">
                    <i class="fa-solid fa-traffic-light text-amber"></i>
                    <span>Traffic Signal</span>
                </div>
                <div class="signal-popup-body">
                    <div class="popup-meta-row"><span>Route:</span> <strong>${escapeHtml(routeName)}</strong></div>
                    ${nameText}
                    <div class="popup-meta-row"><span>Approx. Position:</span> <strong>~${kmFromStart} km</strong> from start</div>
                    <div class="popup-meta-row"><span>Est. Delay:</span> <strong class="text-amber">~${sig.estimated_delay_s || 45} sec</strong></div>
                    ${osmIdText}
                </div>
                <div class="signal-popup-disclaimer">
                    Estimated delay based on 45s baseline. OpenStreetMap provides physical signal locations, not live phases.
                </div>
            </div>
        `;

        return L.marker([sig.latitude, sig.longitude], { icon: signalIcon }).bindPopup(popupHtml, {
            maxWidth: 280,
            className: 'custom-signal-popup'
        });
    }

    function toggleSignals(isVisible) {
        areSignalsVisible = isVisible;
        if (isVisible) {
            renderSignalsForSelectedRoute();
        } else {
            signalLayerGroup.clearLayers();
            signalCountBadge.style.display = 'none';
        }
    }

    // ==========================================
    // 8. Select Route Action
    // ==========================================
    function selectRoute(routeId) {
        selectedRouteId = routeId;
        updateRouteStyles();
        renderSignalsForSelectedRoute();
        updateCardAndTableSelectionState();
    }

    function updateCardAndTableSelectionState() {
        // Update Route Cards UI
        document.querySelectorAll('.route-card').forEach(card => {
            const rId = card.dataset.routeId;
            const isSel = (rId === selectedRouteId);

            card.classList.toggle('is-selected', isSel);

            const btn = card.querySelector('.btn-select-route');
            if (btn) {
                btn.innerHTML = isSel ? `<i class="fa-solid fa-check"></i> SELECTED` : `<i class="fa-solid fa-hand-pointer"></i> SELECT ROUTE`;
            }

            const badgesWrapper = card.querySelector('.card-badges-wrapper');
            if (badgesWrapper) {
                let selBadge = badgesWrapper.querySelector('.selected-badge');
                if (isSel && !selBadge) {
                    selBadge = document.createElement('div');
                    selBadge.className = 'selected-badge';
                    selBadge.innerHTML = `<i class="fa-solid fa-check"></i> SELECTED`;
                    badgesWrapper.appendChild(selBadge);
                } else if (!isSel && selBadge) {
                    selBadge.remove();
                }
            }
        });

        // Update Comparison Table UI
        document.querySelectorAll('#comparisonTableBody tr').forEach(row => {
            const rId = row.dataset.routeId;
            row.classList.toggle('row-selected', rId === selectedRouteId);
        });
    }

    // ==========================================
    // 9. Route Comparison Table
    // ==========================================
    function renderRouteComparisonTable(routes) {
        comparisonTableBody.innerHTML = '';
        if (!routes || routes.length === 0) return;

        routes.forEach(r => {
            const rId = r.route_id || `route_${r.id}`;
            const isOpt = (rId === optimizedRouteId);
            const isSel = (rId === selectedRouteId);

            const tr = document.createElement('tr');
            tr.dataset.routeId = rId;
            tr.className = isSel ? 'row-selected' : '';

            const totalEstMin = r.effective_duration_min || (r.duration_min + r.estimated_signal_delay_min).toFixed(1);
            const scoreVal = r.scores ? r.scores.total : r.optimization_score;

            tr.innerHTML = `
                <td>
                    <strong>${escapeHtml(r.name)}</strong>
                    ${isOpt ? ' <span class="text-green" title="Optimized Route">★</span>' : ''}
                </td>
                <td>${r.distance_km} km</td>
                <td>${r.duration_min}m</td>
                <td>${r.signal_count}</td>
                <td>${r.estimated_signal_delay_min}m</td>
                <td><strong>${totalEstMin}m</strong></td>
                <td><strong class="${isOpt ? 'text-green' : ''}">${scoreVal}</strong></td>
            `;

            tr.addEventListener('click', () => {
                selectRoute(rId);
            });

            comparisonTableBody.appendChild(tr);
        });
    }

    // ==========================================
    // 10. Route Comparison Cards
    // ==========================================
    function updateRouteCards(routes) {
        routesContainer.innerHTML = '';

        if (!routes || routes.length === 0) {
            routesContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-route empty-icon"></i>
                    <h3>No Routes Found</h3>
                    <p>No driving path exists between the selected points.</p>
                </div>`;
            return;
        }

        const minDur = Math.min(...routes.map(r => r.duration_s || (r.duration_min * 60)));
        const minSig = Math.min(...routes.map(r => r.signal_count));
        const minDist = Math.min(...routes.map(r => r.distance_m || (r.distance_km * 1000)));

        routes.forEach(r => {
            const rId = r.route_id || `route_${r.id}`;
            const isOpt = (rId === optimizedRouteId);
            const isSel = (rId === selectedRouteId);
            const rDur = r.duration_s || (r.duration_min * 60);
            const rDist = r.distance_m || (r.distance_km * 1000);

            const card = document.createElement('div');
            card.className = `route-card ${isOpt ? 'is-optimized' : ''} ${isSel ? 'is-selected' : ''}`;
            card.dataset.routeId = rId;

            const totalEstMin = r.effective_duration_min || (r.duration_min + r.estimated_signal_delay_min).toFixed(1);
            const scoreVal = r.scores ? r.scores.total : r.optimization_score;

            const scoreBreakdown = r.scores
                ? `Time: ${r.scores.time} • Signals: ${r.scores.signals} • Dist: ${r.scores.distance}`
                : `Composite Score: ${scoreVal}`;

            // Contextual badges
            let extraBadges = '';
            if (routes.length > 1) {
                if (rDur <= minDur) {
                    extraBadges += `<div class="metric-badge badge-fastest"><i class="fa-solid fa-bolt"></i> FASTEST</div>`;
                }
                if (r.signal_count <= minSig) {
                    extraBadges += `<div class="metric-badge badge-fewest-signals"><i class="fa-solid fa-traffic-light"></i> FEWEST SIGNALS</div>`;
                }
                if (rDist <= minDist) {
                    extraBadges += `<div class="metric-badge badge-shortest"><i class="fa-solid fa-ruler-horizontal"></i> SHORTEST</div>`;
                }
            }

            card.innerHTML = `
                <div class="card-badges-wrapper">
                    ${isOpt ? `
                        <div class="optimized-badge">
                            <i class="fa-solid fa-star"></i> RECOMMENDED OPTIMIZED
                        </div>
                    ` : ''}
                    ${extraBadges}
                    ${isSel ? `
                        <div class="selected-badge">
                            <i class="fa-solid fa-check"></i> ACTIVE
                        </div>
                    ` : ''}
                </div>

                <div class="route-header">
                    <span class="route-title">${escapeHtml(r.name)}</span>
                    <span class="route-score-tag" title="${scoreBreakdown}">Score: ${scoreVal}</span>
                </div>

                <div class="route-grid">
                    <div class="metric-item">
                        <span class="metric-label"><i class="fa-solid fa-ruler"></i> Distance</span>
                        <span class="metric-value">${r.distance_km} km</span>
                    </div>

                    <div class="metric-item">
                        <span class="metric-label"><i class="fa-solid fa-car"></i> Driving Time</span>
                        <span class="metric-value highlight-cyan">${r.duration_min} min</span>
                    </div>

                    <div class="metric-item">
                        <span class="metric-label"><i class="fa-solid fa-traffic-light"></i> Traffic Signals</span>
                        <span class="metric-value">${r.signal_count}</span>
                    </div>

                    <div class="metric-item">
                        <span class="metric-label"><i class="fa-solid fa-hourglass-half"></i> Est. Signal Delay</span>
                        <span class="metric-value highlight-amber">~${r.estimated_signal_delay_min} min</span>
                    </div>

                    <div class="metric-item metric-effective">
                        <span class="metric-label"><i class="fa-solid fa-clock"></i> Est. Effective Travel Time:</span>
                        <span class="metric-value">${totalEstMin} min</span>
                    </div>
                </div>

                ${isOpt ? `
                    <p style="font-size:11px; color:var(--text-muted); margin-top:8px;">
                        <i class="fa-solid fa-circle-check text-green"></i> Lowest composite score balancing duration, signals, and distance.
                    </p>
                ` : ''}

                <div class="card-action-bar">
                    <button type="button" class="btn-select-route">
                        ${isSel ? `<i class="fa-solid fa-check"></i> SELECTED` : `<i class="fa-solid fa-hand-pointer"></i> SELECT ROUTE`}
                    </button>
                </div>
            `;

            card.addEventListener('click', () => {
                selectRoute(rId);
            });

            routesContainer.appendChild(card);
        });
    }

    // ==========================================
    // 11. Fit Map Bounds
    // ==========================================
    function fitRoutesToBounds() {
        const bounds = L.latLngBounds();

        if (startLocation) {
            bounds.extend([startLocation.latitude, startLocation.longitude]);
        }
        if (destLocation) {
            bounds.extend([destLocation.latitude, destLocation.longitude]);
        }

        Object.values(routeLayersMap).forEach(layer => {
            const b = layer.getBounds();
            if (b.isValid()) {
                bounds.extend(b);
            }
        });

        if (bounds.isValid()) {
            map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
        }
    }

    function clearRoutes() {
        Object.keys(routeLayersMap).forEach(key => delete routeLayersMap[key]);
        alternativeRouteGroup.clearLayers();
        optimizedRouteGroup.clearLayers();
        signalLayerGroup.clearLayers();
    }

    // ==========================================
    // 12. UI Helpers & Error Alerts
    // ==========================================
    function setLoadingState(isLoading, message = "Calculating optimal routes...") {
        findRoutesBtn.disabled = isLoading;
        if (isLoading) {
            findRoutesBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> CALCULATING...`;
            mapStatusOverlay.style.display = 'flex';
            mapStatusText.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(message)}`;
        } else {
            findRoutesBtn.innerHTML = `<i class="fa-solid fa-compass"></i> FIND ROUTES`;
            mapStatusOverlay.style.display = 'none';
        }
    }

    function showAlert(msg, type = "warning") {
        const div = document.createElement('div');
        div.className = `alert alert-${type}`;
        const icon = type === "error" ? "fa-circle-exclamation" : "fa-triangle-exclamation";
        div.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(msg)}</span>`;
        alertContainer.appendChild(div);
    }

    function clearAlerts() {
        alertContainer.innerHTML = '';
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.toString().replace(/[&<>"']/g, m => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        })[m]);
    }

    // Initialize application
    initializeMap();
    setupSearch();
});
