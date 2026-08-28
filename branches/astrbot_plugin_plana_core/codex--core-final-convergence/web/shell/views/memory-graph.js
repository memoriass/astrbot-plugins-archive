window.PlanaMemoryGraph = (() => {
  const CATEGORY_LABELS = { topic: '\u4e3b\u9898', person: '\u7528\u6237\u4e0e\u753b\u50cf', fact: '\u4e8b\u5b9e\u4e0e\u504f\u597d', summary: '\u8bb0\u5fc6\u4e0e\u6d41\u7a0b', other: '\u5176\u4ed6' };
  const CATEGORY_COLORS = { topic: '#7c6fca', person: '#2f9e8b', fact: '#c99a16', summary: '#c8648d', other: '#8b949e' };

  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

  const hash = (value) => { let result = 0; for (const character of String(value || '')) result = (result * 31 + character.charCodeAt(0)) % 104729; return result / 104729; };
  const shorten = (value, length = 18) => { const text = String(value || ''); return text.length > length ? `${text.slice(0, length - 1)}\u2026` : text; };
  const summaryText = (value, length = 720) => { const text = String(value || '').replace(/\s+/g, ' ').trim(); return text.length > length ? `${text.slice(0, length)}\u2026` : text; };

  const conceptKind = (node) => {
    const value = `${node.concept || ''} ${String(node.memory_items || '').slice(0, 240)}`.toLowerCase();
    if (/user|person|profile|\u7528\u6237|\u753b\u50cf|\u6635\u79f0|\u79f0\u547c|\u5bb6\u4eba|\u670b\u53cb/.test(value)) return 'person';
    if (/fact|preference|risk|\u504f\u597d|\u98ce\u9669|\u559c\u6b22|\u4e60\u60ef|\u996e\u98df|\u63d0\u9192/.test(value)) return 'fact';
    if (/summary|workflow|memory|\u5de5\u4f5c\u6d41|\u8bb0\u5fc6|\u4efb\u52a1|\u6d41\u7a0b|\u8ba1\u5212/.test(value)) return 'summary';
    return node.concept ? 'topic' : 'other';
  };

  function prepareGraph(data) {
    const rawNodes = Array.isArray(data.nodes) ? data.nodes : [];
    const rawEdges = Array.isArray(data.edges) ? data.edges : [];
    const degreeByName = new Map();

    for (const edge of rawEdges) {
      degreeByName.set(edge.source, (degreeByName.get(edge.source) || 0) + 1);
      degreeByName.set(edge.target, (degreeByName.get(edge.target) || 0) + 1);
    }

    const nodes = rawNodes
      .map((node) => ({
        ...node,
        id: String(node.id ?? node.concept),
        name: String(node.concept || node.id || '\u672a\u547d\u540d\u4e3b\u9898'),
        weight: Number(node.weight || 1),
        degree: degreeByName.get(node.concept) || 0,
        kind: conceptKind(node),
      }))
      .sort((left, right) => (right.weight + right.degree * 0.7) - (left.weight + left.degree * 0.7))
      .slice(0, 120)
      .map((node, rank) => ({
        ...node,
        rank,
        radius: clamp(4.5 + Math.sqrt(node.weight) * 1.15 + Math.sqrt(node.degree) * 0.7, 5, 14),
        x: (hash(`${node.id}:x`) - 0.5) * 560,
        y: (hash(`${node.id}:y`) - 0.5) * 440,
        velocityX: 0,
        velocityY: 0,
      }));

    const nodeByName = new Map(nodes.map((node) => [node.name, node]));
    const edges = rawEdges
      .map((edge) => ({
        ...edge,
        sourceNode: nodeByName.get(edge.source),
        targetNode: nodeByName.get(edge.target),
        weight: Number(edge.strength || 1),
      }))
      .filter((edge) => edge.sourceNode && edge.targetNode && edge.sourceNode !== edge.targetNode)
      .slice(0, 240);

    const neighbors = new Map(nodes.map((node) => [node, new Set()]));
    for (const edge of edges) {
      neighbors.get(edge.sourceNode).add(edge.targetNode);
      neighbors.get(edge.targetNode).add(edge.sourceNode);
    }

    return { nodes, edges, neighbors };
  }

  function solveLayout(nodes, edges) {
    const iterations = nodes.length > 100 ? 170 : nodes.length > 60 ? 230 : 320;
    for (let step = 0; step < iterations; step += 1) {
      const cooling = 0.35 + (1 - step / iterations) * 0.65;
      for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
          const leftNode = nodes[leftIndex];
          const rightNode = nodes[rightIndex];
          const deltaX = leftNode.x - rightNode.x;
          const deltaY = leftNode.y - rightNode.y;
          const distanceSquared = Math.max(deltaX * deltaX + deltaY * deltaY, 80);
          const distance = Math.sqrt(distanceSquared);
          const minimumDistance = (leftNode.radius + rightNode.radius) * 2.1 + 14;
          const interactionRange = 280 + Math.min(120, nodes.length);
          let force = 1600 * cooling / distanceSquared;
          if (distance > interactionRange) force *= 0.04;
          if (distance < minimumDistance) force += (minimumDistance - distance) * 0.32;
          leftNode.velocityX += deltaX / distance * force;
          rightNode.velocityX -= deltaX / distance * force;
          leftNode.velocityY += deltaY / distance * force;
          rightNode.velocityY -= deltaY / distance * force;
        }
      }

      for (const edge of edges) {
        const deltaX = edge.targetNode.x - edge.sourceNode.x;
        const deltaY = edge.targetNode.y - edge.sourceNode.y;
        const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY) || 1;
        const desiredDistance = 132 - clamp(edge.weight, 1, 8) * 7 + hash(`${edge.sourceNode.id}${edge.targetNode.id}`) * 28;
        const force = (distance - desiredDistance) * 0.018 * cooling;
        edge.sourceNode.velocityX += deltaX / distance * force;
        edge.sourceNode.velocityY += deltaY / distance * force;
        edge.targetNode.velocityX -= deltaX / distance * force;
        edge.targetNode.velocityY -= deltaY / distance * force;
      }

      for (const node of nodes) {
        const mass = 1 + Math.sqrt(node.weight) * 0.12 + Math.sqrt(node.degree) * 0.08;
        node.velocityX = (node.velocityX - node.x * 0.007 / mass) * 0.82;
        node.velocityY = (node.velocityY - node.y * 0.007 / mass) * 0.82;
        const speed = Math.hypot(node.velocityX, node.velocityY);
        if (speed > 14) {
          node.velocityX = node.velocityX / speed * 14;
          node.velocityY = node.velocityY / speed * 14;
        }
        node.x += node.velocityX;
        node.y += node.velocityY;
      }
    }
  }

  function mount({ canvas, detail, root, data, ctx }) {
    if (!canvas || !detail) return () => {};

    const drawingContext = canvas.getContext('2d');
    const { nodes, edges, neighbors } = prepareGraph(data);
    if (!nodes.length) return () => {};
    solveLayout(nodes, edges);

    const computedStyle = getComputedStyle(document.documentElement);
    const palette = {
      line: computedStyle.getPropertyValue('--line').trim() || '#34415a',
      text: computedStyle.getPropertyValue('--text').trim() || '#eef4ff',
      muted: computedStyle.getPropertyValue('--muted').trim() || '#98a4b8',
      paper: computedStyle.getPropertyValue('--paper').trim() || '#111a2c',
      focus: '#e0a82e',
    };

    const searchInput = root.querySelector('#concept-search');
    const labelButton = root.querySelector('[data-map-action="labels"]');
    const status = root.querySelector('#concept-map-status');
    let selectedNode = null;
    let hoveredNode = null;
    let labelsVisible = true;
    let animationFrame = 0;
    let fitScale = 1;
    let fitOffsetX = 0;
    let fitOffsetY = 0;
    let zoom = 1;
    let panX = 0;
    let panY = 0;
    let dragState = null;
    let suppressClick = false;

    const relatedNodes = () => {
      const focusedNode = hoveredNode || selectedNode;
      if (!focusedNode) return null;
      return new Set([focusedNode, ...(neighbors.get(focusedNode) || [])]);
    };

    const resize = () => {
      const rectangle = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(320, Math.floor(rectangle.width * ratio));
      canvas.height = Math.max(300, Math.floor(rectangle.height * ratio));
      drawingContext.setTransform(ratio, 0, 0, ratio, 0, 0);

      const xValues = nodes.map((node) => node.x);
      const yValues = nodes.map((node) => node.y);
      const minimumX = Math.min(...xValues);
      const maximumX = Math.max(...xValues);
      const minimumY = Math.min(...yValues);
      const maximumY = Math.max(...yValues);
      fitScale = Math.min(
        1.25,
        (rectangle.width - 96) / Math.max(1, maximumX - minimumX),
        (rectangle.height - 88) / Math.max(1, maximumY - minimumY),
      );
      fitOffsetX = rectangle.width / 2 - fitScale * (minimumX + maximumX) / 2;
      fitOffsetY = rectangle.height / 2 - fitScale * (minimumY + maximumY) / 2;
    };

    const project = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      for (const node of nodes) {
        const fittedX = node.x * fitScale + fitOffsetX;
        const fittedY = node.y * fitScale + fitOffsetY;
        node.screenX = width / 2 + panX + (fittedX - width / 2) * zoom;
        node.screenY = height / 2 + panY + (fittedY - height / 2) * zoom;
      }
    };

    const updateStatus = () => {
      if (status) status.textContent = `\u663e\u793a ${nodes.length} \u4e2a\u8282\u70b9 \u00b7 ${edges.length} \u6761\u5173\u8054 \u00b7 ${Math.round(zoom * 100)}%`;
    };

    const updateDetail = (node) => {
      const currentNode = node || selectedNode;
      if (!currentNode) {
        detail.innerHTML = '\u5c06\u6307\u9488\u79fb\u52a8\u5230\u8282\u70b9\u4e0a\u67e5\u770b\u8be6\u60c5\u3002';
        return;
      }
      detail.innerHTML = `<b>${ctx.esc(currentNode.name)}</b><span>${CATEGORY_LABELS[currentNode.kind]} \u00b7 \u6743\u91cd ${ctx.esc(currentNode.weight)} \u00b7 \u5173\u8054 ${ctx.esc(currentNode.degree)}</span><p>${ctx.esc(summaryText(currentNode.memory_items || '\u6682\u65e0\u5173\u8054\u8bb0\u5fc6\u6458\u8981\u3002'))}</p>`;
    };

    const drawRoundedLabel = (text, x, y, active) => {
      const fontSize = active ? 12 : 11;
      drawingContext.font = `${active ? '650' : '550'} ${fontSize}px Inter, sans-serif`;
      const width = drawingContext.measureText(text).width + 12;
      const height = fontSize + 8;
      drawingContext.globalAlpha = active ? 0.94 : 0.82;
      drawingContext.fillStyle = palette.paper;
      drawingContext.beginPath();
      drawingContext.roundRect(x, y - height / 2, width, height, 5);
      drawingContext.fill();
      drawingContext.globalAlpha = 1;
      drawingContext.fillStyle = active ? palette.text : palette.muted;
      drawingContext.fillText(text, x + 6, y + fontSize * 0.34);
      return { x1: x, y1: y - height / 2, x2: x + width, y2: y + height / 2 };
    };

    const draw = () => {
      project();
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const focusedNode = hoveredNode || selectedNode;
      const visibleNodes = relatedNodes();
      const labelBoxes = [];
      drawingContext.clearRect(0, 0, width, height);
      drawingContext.lineCap = 'round';

      for (const edge of edges) {
        const isAdjacent = focusedNode && (edge.sourceNode === focusedNode || edge.targetNode === focusedNode);
        const isVisible = !visibleNodes || (visibleNodes.has(edge.sourceNode) && visibleNodes.has(edge.targetNode));
        const midpointX = (edge.sourceNode.screenX + edge.targetNode.screenX) / 2;
        const midpointY = (edge.sourceNode.screenY + edge.targetNode.screenY) / 2;
        const deltaX = edge.targetNode.screenX - edge.sourceNode.screenX;
        const deltaY = edge.targetNode.screenY - edge.sourceNode.screenY;
        const curve = (hash(edge.id || `${edge.source}${edge.target}`) - 0.5) * 20 * clamp(zoom, 0.8, 1.5);
        const length = Math.hypot(deltaX, deltaY) || 1;
        const controlX = midpointX - deltaY / length * curve;
        const controlY = midpointY + deltaX / length * curve;
        drawingContext.strokeStyle = isAdjacent ? CATEGORY_COLORS[focusedNode.kind] : palette.line;
        drawingContext.globalAlpha = isAdjacent ? 0.66 : isVisible ? 0.15 : 0.035;
        drawingContext.lineWidth = isAdjacent ? 1.8 : clamp(0.65 + edge.weight * 0.12, 0.7, 1.35);
        drawingContext.beginPath();
        drawingContext.moveTo(edge.sourceNode.screenX, edge.sourceNode.screenY);
        drawingContext.quadraticCurveTo(controlX, controlY, edge.targetNode.screenX, edge.targetNode.screenY);
        drawingContext.stroke();
      }

      drawingContext.globalAlpha = 1;
      for (const node of nodes) {
        const isFocused = node === focusedNode;
        const isSelected = node === selectedNode;
        const isRelated = !visibleNodes || visibleNodes.has(node);
        const radius = node.radius * clamp(Math.sqrt(zoom), 0.82, 1.45) * (isFocused ? 1.2 : 1);
        const color = CATEGORY_COLORS[node.kind] || CATEGORY_COLORS.other;
        drawingContext.globalAlpha = isRelated ? 1 : 0.2;

        if (node.rank < 3 || isFocused || isSelected) {
          drawingContext.strokeStyle = node.rank < 3 ? palette.focus : color;
          drawingContext.lineWidth = isFocused || isSelected ? 2.4 : 1.5;
          drawingContext.beginPath();
          drawingContext.arc(node.screenX, node.screenY, radius + (isFocused ? 6 : 3), 0, Math.PI * 2);
          drawingContext.stroke();
        }

        drawingContext.fillStyle = color;
        drawingContext.strokeStyle = palette.paper;
        drawingContext.lineWidth = 1.2;
        drawingContext.beginPath();
        drawingContext.arc(node.screenX, node.screenY, radius, 0, Math.PI * 2);
        drawingContext.fill();
        drawingContext.stroke();
        drawingContext.globalAlpha = 1;

        const showLabel = labelsVisible && (
          isFocused || isSelected ||
          (visibleNodes && isRelated && node.degree > 0) ||
          (zoom >= 1.15 && (node.rank < 12 || node.degree >= 5)) ||
          (zoom < 1.15 && node.rank < 7)
        );
        if (!showLabel) continue;

        const label = shorten(node.name, isFocused || isSelected ? 28 : 18);
        const labelX = node.screenX + radius + 7;
        const labelY = node.screenY;
        drawingContext.font = `${isFocused || isSelected ? '650' : '550'} ${isFocused || isSelected ? 12 : 11}px Inter, sans-serif`;
        const measuredWidth = drawingContext.measureText(label).width + 12;
        const prospectiveBox = { x1: labelX, y1: labelY - 10, x2: labelX + measuredWidth, y2: labelY + 10 };
        const collides = labelBoxes.some((box) => prospectiveBox.x1 <= box.x2 && prospectiveBox.x2 >= box.x1 && prospectiveBox.y1 <= box.y2 && prospectiveBox.y2 >= box.y1);
        const inViewport = prospectiveBox.x1 > 0 && prospectiveBox.x2 < width && prospectiveBox.y1 > 0 && prospectiveBox.y2 < height;
        if ((isFocused || isSelected || !collides) && inViewport) labelBoxes.push(drawRoundedLabel(label, labelX, labelY, isFocused || isSelected));
      }
      updateStatus();
    };

    const scheduleDraw = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(draw);
    };

    const findNodeAt = (clientX, clientY) => {
      const rectangle = canvas.getBoundingClientRect();
      const pointerX = clientX - rectangle.left;
      const pointerY = clientY - rectangle.top;
      return nodes.find((node) => Math.hypot(node.screenX - pointerX, node.screenY - pointerY) <= node.radius * clamp(Math.sqrt(zoom), 0.82, 1.45) + 8) || null;
    };

    const focusNode = (node) => {
      if (!node) return;
      selectedNode = node;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const fittedX = node.x * fitScale + fitOffsetX;
      const fittedY = node.y * fitScale + fitOffsetY;
      zoom = Math.max(zoom, 1.25);
      panX = -(fittedX - width / 2) * zoom;
      panY = -(fittedY - height / 2) * zoom;
      updateDetail(selectedNode);
      scheduleDraw();
    };

    const resetView = () => {
      zoom = 1;
      panX = 0;
      panY = 0;
      hoveredNode = null;
      selectedNode = null;
      updateDetail(selectedNode);
      scheduleDraw();
    };

    const zoomAtCenter = (factor) => {
      zoom = clamp(zoom * factor, 0.55, 4.5);
      scheduleDraw();
    };

    const onWheel = (event) => {
      event.preventDefault();
      const rectangle = canvas.getBoundingClientRect();
      const pointerX = event.clientX - rectangle.left;
      const pointerY = event.clientY - rectangle.top;
      const centerX = canvas.clientWidth / 2;
      const centerY = canvas.clientHeight / 2;
      const previousZoom = zoom;
      const nextZoom = clamp(zoom * (event.deltaY < 0 ? 1.12 : 0.89), 0.55, 4.5);
      const baseX = (pointerX - centerX - panX) / previousZoom;
      const baseY = (pointerY - centerY - panY) / previousZoom;
      zoom = nextZoom;
      panX = pointerX - centerX - baseX * zoom;
      panY = pointerY - centerY - baseY * zoom;
      scheduleDraw();
    };

    const onPointerDown = (event) => {
      dragState = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        initialPanX: panX,
        initialPanY: panY,
        hitNode: findNodeAt(event.clientX, event.clientY),
      };
      suppressClick = false;
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add('is-dragging');
    };

    const onPointerMove = (event) => {
      if (dragState && dragState.pointerId === event.pointerId) {
        const deltaX = event.clientX - dragState.startX;
        const deltaY = event.clientY - dragState.startY;
        if (Math.hypot(deltaX, deltaY) > 4) suppressClick = true;
        if (suppressClick) {
          panX = dragState.initialPanX + deltaX;
          panY = dragState.initialPanY + deltaY;
          scheduleDraw();
        }
        return;
      }

      const nextHoveredNode = findNodeAt(event.clientX, event.clientY);
      if (nextHoveredNode !== hoveredNode) {
        hoveredNode = nextHoveredNode;
        canvas.classList.toggle('has-node-hover', Boolean(hoveredNode));
        updateDetail(hoveredNode || selectedNode);
        scheduleDraw();
      }
    };

    const onPointerUp = (event) => {
      if (!dragState || dragState.pointerId !== event.pointerId) return;
      if (!suppressClick && dragState.hitNode) {
        selectedNode = dragState.hitNode;
        updateDetail(selectedNode);
        scheduleDraw();
      }
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      canvas.classList.remove('is-dragging');
      dragState = null;
    };

    const onPointerLeave = () => {
      if (dragState) return;
      hoveredNode = null;
      canvas.classList.remove('has-node-hover');
      updateDetail(selectedNode);
      scheduleDraw();
    };

    const onKeyDown = (event) => {
      const panStep = 28;
      if (event.key === 'Escape') resetView();
      else if (event.key === '+' || event.key === '=') zoomAtCenter(1.15);
      else if (event.key === '-') zoomAtCenter(0.87);
      else if (event.key === 'ArrowLeft') panX += panStep;
      else if (event.key === 'ArrowRight') panX -= panStep;
      else if (event.key === 'ArrowUp') panY += panStep;
      else if (event.key === 'ArrowDown') panY -= panStep;
      else return;
      event.preventDefault();
      scheduleDraw();
    };

    const onSearch = () => {
      const query = String(searchInput?.value || '').trim().toLowerCase();
      if (!query) return;
      const match = nodes.find((node) => node.name.toLowerCase() === query) || nodes.find((node) => node.name.toLowerCase().includes(query));
      if (match) {
        focusNode(match);
        searchInput.setCustomValidity('');
      } else {
        searchInput.setCustomValidity('\u672a\u627e\u5230\u5339\u914d\u8282\u70b9');
        searchInput.reportValidity();
      }
    };

    const actionHandlers = {
      'zoom-in': () => zoomAtCenter(1.18),
      'zoom-out': () => zoomAtCenter(0.84),
      reset: resetView,
      labels: () => {
        labelsVisible = !labelsVisible;
        labelButton?.setAttribute('aria-pressed', String(labelsVisible));
        labelButton?.classList.toggle('active', labelsVisible);
        scheduleDraw();
      },
      search: onSearch,
    };

    const actionButtons = [...root.querySelectorAll('[data-map-action]')];
    const onAction = (event) => actionHandlers[event.currentTarget.dataset.mapAction]?.();
    for (const button of actionButtons) button.addEventListener('click', onAction);
    const onSearchKeyDown = (event) => {
      if (event.key === 'Enter') onSearch();
    };
    const clearSearchValidity = () => searchInput?.setCustomValidity('');
    searchInput?.addEventListener('keydown', onSearchKeyDown);
    searchInput?.addEventListener('input', clearSearchValidity);

    const onResize = () => {
      resize();
      scheduleDraw();
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerUp);
    canvas.addEventListener('pointerleave', onPointerLeave);
    canvas.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onResize, { passive: true });

    resize();
    updateDetail(selectedNode);
    draw();

    return () => {
      cancelAnimationFrame(animationFrame);
      for (const button of actionButtons) button.removeEventListener('click', onAction);
      searchInput?.removeEventListener('keydown', onSearchKeyDown);
      searchInput?.removeEventListener('input', clearSearchValidity);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('pointerleave', onPointerLeave);
      canvas.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onResize);
    };
  }

  return { mount };
})();
