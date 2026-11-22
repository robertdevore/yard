'use strict';

const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="yard-token"]').content;
const dialog = $('dialog');
const panel = $('dialog-content');
const history = new Map();
const busy = new Map();
let current = [];
let loading;
let view = 'services';
let returnFocus;
let noticeTimer;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function button(text, action, className) {
  const node = element('button', text, className);
  node.type = 'button';
  node.addEventListener('click', action);
  return node;
}

function link(url, label) {
  try {
    const target = new URL(url);
    if (!['http:', 'https:'].includes(target.protocol)) return null;
    const node = element('a', label, 'action-link');
    node.href = target.href;
    node.target = '_blank';
    node.rel = 'noopener noreferrer';
    return node;
  } catch {
    return null;
  }
}

async function request(path, body) {
  const options = body ? {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({...body, token}),
  } : {};
  const response = await fetch(path, options);
  if (response.status === 403) throw new Error('Yard rejected this request. Reload the dashboard and try again.');
  const data = await response.json();
  if (!response.ok || (data.ok === false && !data.needs_confirm)) throw new Error(data.error || 'Yard could not complete this request.');
  return data;
}

function notice(message, error = false) {
  clearTimeout(noticeTimer);
  const node = $('notice');
  node.textContent = message;
  node.classList.toggle('error', error);
  node.hidden = false;
  if (!error) noticeTimer = setTimeout(() => { node.hidden = true; }, 6000);
}

function health(service) {
  const labels = {
    healthy: service.http_status ? `HTTP ${service.http_status}` : 'TCP reachable',
    process: 'Process verified',
    not_http: 'Sensitive • probe skipped',
    not_checked: 'No health probe',
    unhealthy: `HTTP ${service.http_status || 'error'}`,
    timeout: 'Health request timed out',
    connection_failed: 'Connection failed',
    pending: 'Probe pending',
    unknown: '',
  };
  const label = labels[service.health_status] ?? service.health_status;
  return `${label}${service.response_ms != null ? ` · ${service.response_ms} ms` : ''}`;
}

function classify(service) {
  if (busy.has(service.id)) return [busy.get(service.id), 'attention', 'warn'];
  if (service.untracked) return ['External listener', 'attention', 'warn'];
  if (service.state === 'stopped') {
    return [service.enabled ? 'Stopped' : 'Disabled', 'stopped', ''];
  }
  if (service.state === 'running') {
    if (['unhealthy', 'timeout', 'connection_failed', 'not_http'].includes(service.health_status) && !service.sensitive) {
      return ['Unhealthy', 'attention', 'warn'];
    }
    if (service.diagnostic) return ['Needs attention', 'attention', 'warn'];
    return [service.health_status === 'healthy' ? 'Healthy' : 'Running', 'running', 'good'];
  }
  const labels = {starting: 'Starting', stopping: 'Stopping', failed: 'Failed', unknown: 'Unknown'};
  return [labels[service.state] || 'Unknown', 'attention', 'warn'];
}

function switchView(next) {
  view = next;
  for (const name of ['services', 'discovery']) {
    $(`${name}-panel`).hidden = next !== name;
    const tab = $(`${name}-tab`);
    if (next === name) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  }
}

function render() {
  const registered = current.filter(service => service.managed);
  const listeners = current.filter(service => !service.managed);
  const totals = {running: 0, stopped: 0, attention: 0};
  for (const service of registered) totals[classify(service)[1]]++;
  for (const key of Object.keys(totals)) $(key).textContent = totals[key];
  $('service-count').textContent = registered.length;
  $('discovery-count').textContent = listeners.length;
  const selectedGroup = $('group').value;
  const selectedStatus = $('status').value;
  for (const metric of document.querySelectorAll('[data-status]')) {
    metric.setAttribute('aria-pressed', String(metric.dataset.status === selectedStatus));
  }
  const groups = [...new Set(registered.map(service => service.group))].sort();
  if (groups.join('\0') !== [...$('group').options].slice(1).map(option => option.value).join('\0')) {
    $('group').replaceChildren(new Option('All groups', ''), ...groups.map(group => new Option(group)));
    $('group').value = groups.includes(selectedGroup) ? selectedGroup : '';
  }
  const query = $('search').value.toLowerCase().trim();
  const shown = registered.filter(service =>
    (!$('group').value || service.group === $('group').value) &&
    (!selectedStatus || (selectedStatus === 'external' ? service.untracked : classify(service)[1] === selectedStatus)) &&
    (!query || [service.name, service.description, service.group, service.port, service.id].join(' ').toLowerCase().includes(query))
  );
  const nameSort = (a, b) => a.name.localeCompare(b.name);
  const sorters = {
    name: nameSort,
    port: (a, b) => (a.port ?? Infinity) - (b.port ?? Infinity) || nameSort(a, b),
    state: (a, b) => classify(a)[0].localeCompare(classify(b)[0]) || nameSort(a, b),
    favorite: (a, b) => Number(b.favorite) - Number(a.favorite) || nameSort(a, b),
  };
  shown.sort(sorters[$('sort').value]);
  const list = $('services');
  const focused = list.contains(document.activeElement) ? document.activeElement : null;
  const keyed = focused?.dataset.focus;
  const focusedService = focused?.closest('li')?.dataset.service;
  // Leaving unchanged DOM in place preserves keyboard and screen-reader position.
  const signature = JSON.stringify(shown.map(service => [service, busy.get(service.id)]));
  if (list.dataset.signature !== signature) {
    list.dataset.signature = signature;
    const empty = registered.length ? 'No services match these filters.' : 'No registered services. Choose Add Service or look in Discovery.';
    list.replaceChildren(...(shown.length ? shown.map(serviceRow) : [element('li', empty, 'empty')]));
    if (keyed) {
      const alternatives = [...list.querySelectorAll('[data-focus]')];
      const restored = alternatives.find(node => node.dataset.focus === keyed && !node.disabled) ??
        alternatives.find(node => node.dataset.focus === `${focusedService}-details`);
      (restored ?? $('search')).focus({preventScroll: true});
    }
  }
  const listenerList = $('listeners');
  const listenerSignature = JSON.stringify(listeners);
  if (listenerList.dataset.signature !== listenerSignature && !listenerList.contains(document.activeElement)) {
    listenerList.dataset.signature = listenerSignature;
    listenerList.replaceChildren(...(listeners.length ? listeners.map(listenerRow) :
      [element('li', 'No unregistered listeners found.', 'empty')]));
  }
}

function serviceRow(service) {
  const row = element('li', null, 'service-row');
  row.dataset.service = service.id;
  const name = element('div', null, 'name-block');
  const details = button(service.name, () => serviceDetails(service), 'name-button');
  details.dataset.focus = `${service.id}-details`;
  if (service.favorite) {
    const star = element('span', '★', 'favorite');
    star.setAttribute('aria-label', 'Favorite');
    name.append(star);
  }
  name.append(details, element('p', service.description || (service.group === 'Ungrouped' ? '' : service.group)));
  const [label, , style] = classify(service);
  const state = element('div', null, 'status');
  state.append(element('span', null, `dot ${style}`), document.createTextNode(label));
  if (!busy.has(service.id) && health(service) && service.state === 'running') state.append(element('small', health(service)));
  const port = element('span', service.port ? `:${service.port}` : '—', 'port');
  const actions = element('div', null, 'row-actions');
  if (service.actions.open) {
    const open = link(service.open_url, 'Open');
    if (open) {
      open.dataset.focus = `${service.id}-open`;
      open.setAttribute('aria-label', `Open ${service.name}`);
      actions.append(open);
    }
  }
  if (service.actions.start || service.actions.stop) {
    const action = service.actions.stop ? 'stop' : 'start';
    const label = action === 'stop' ? 'Stop' : service.state === 'failed' ? 'Retry' : 'Start';
    const primary = button(label, () => lifecycle(service, action), action === 'start' ? 'primary' : '');
    primary.dataset.focus = `${service.id}-primary`;
    primary.disabled = busy.has(service.id) || (action === 'stop' && service.state === 'stopping');
    primary.setAttribute('aria-label', `${label} ${service.name}`);
    actions.append(primary);
  }
  const more = button('···', () => serviceDetails(service), 'more');
  more.setAttribute('aria-label', `More actions for ${service.name}`);
  more.dataset.focus = `${service.id}-more`;
  actions.append(more);
  row.append(name, state, port, actions);
  return row;
}

async function refresh() {
  if (loading) return loading;
  $('refresh').disabled = true;
  loading = (async () => {
    try {
      // Partial scans still carry usable status and a diagnostic banner.
      const response = await fetch('/api/services');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      current = data.services;
      for (const service of current.filter(item => item.managed && item.state === 'running')) {
        const label = health(service);
        const samples = history.get(service.id) || [];
        if (label && samples[0]?.time !== data.generated_at) {
          history.set(service.id, [{time: data.generated_at, label}, ...samples].slice(0, 8));
        }
      }
      const diagnostic = [data.scan_error, ...data.config.errors, ...data.config.warnings].filter(Boolean).join(' · ');
      $('diagnostics').textContent = diagnostic;
      $('diagnostics').hidden = !diagnostic;
      $('updated').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      render();
    } catch (error) {
      notice(`Could not refresh Yard. ${error.message}`, true);
    } finally {
      $('refresh').disabled = false;
      loading = null;
    }
  })();
  return loading;
}

function confirmAction(title, text, label) {
  return new Promise(resolve => {
    showDialog(title);
    panel.append(element('p', text));
    const actions = element('div', null, 'dialog-actions');
    const cancel = button('Cancel', () => dialog.close('cancel'));
    actions.append(cancel, button(label, () => dialog.close('yes'), 'primary'));
    panel.append(actions);
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'yes'), {once: true});
    cancel.focus();
  });
}

async function lifecycle(service, action, confirmed = false) {
  if (busy.has(service.id)) return;
  const force = action === 'force';
  if (!confirmed && (force || (action !== 'start' && service.sensitive))) {
    if (!await confirmAction(force ? 'Force Stop' : 'Confirm sensitive service action',
      `${service.name} · process group ${service.process_group}. ${force ? 'Processes may lose unsaved data.' : 'This may interrupt dependent applications.'}`,
      force ? 'Force Stop' : action === 'stop' ? 'Stop service' : 'Restart service')) return;
    confirmed = true;
  }
  busy.set(service.id, force || action === 'stop' ? 'Stopping' : action === 'restart' ? 'Restarting' : 'Starting');
  render();
  let confirmation;
  const path = `/api/services/${encodeURIComponent(service.id)}/${force ? 'stop' : action}`;
  try {
    const data = await request(path, {force, confirm: confirmed, target: confirmed ? service.process_group : null});
    if (data.needs_confirm) confirmation = data.error;
    else if (!data.ok) throw new Error(data.error);
    else notice(`${service.name} · ${data.note || (action === 'restart' ? 'Restarted' : 'Stopped')}`);
  } catch (error) {
    notice(`${service.name} · ${error.message}`, true);
  } finally {
    busy.delete(service.id);
    await refresh();
  }
  if (confirmation && await confirmAction('Confirm action', confirmation, 'Confirm')) {
    const latest = current.find(item => item.id === service.id);
    if (!latest || latest.process_group !== service.process_group) {
      notice('The target changed. Inspect the service before trying again.', true);
      return;
    }
    await lifecycle(latest, action, true);
  }
}

function showDialog(title) {
  if (!dialog.open) returnFocus = document.activeElement;
  dialog.returnValue = '';
  const head = element('div', null, 'dialog-head');
  const heading = element('h2', title);
  heading.id = 'dialog-title';
  const close = button('×', () => dialog.close());
  close.setAttribute('aria-label', 'Close');
  head.append(heading, close);
  panel.replaceChildren(head);
  if (!dialog.open) dialog.showModal();
}

dialog.addEventListener('close', () => {
  if (returnFocus?.isConnected) returnFocus.focus();
  else $('add').focus();
});

function facts(values) {
  const list = element('dl');
  for (const [label, value] of values) {
    if (value != null && value !== '') list.append(element('dt', label), element('dd', value));
  }
  return list;
}

function registryEntries(registry) {
  return Array.isArray(registry) ? registry : registry.services;
}

async function serviceDetails(service) {
  showDialog(service.name);
  const details = element('div');
  panel.append(details);
  if (service.description) details.append(element('p', service.description));
  if (service.diagnostic) details.append(element('p', service.diagnostic, 'error'));
  details.append(facts([
    ['Status', classify(service)[0]], ['Health', health(service)], ['Port', service.port],
    ['URL', service.open_url], ['Process ID', service.pid], ['Parent PID', service.parent_pid],
    ['Process group', service.process_group], ['Executable', service.command], ['Bind address', service.address],
    ['Owning user', service.user], ['Last started', service.started_at], ['Restarts', service.restart_count],
  ]));
  const log = element('pre', 'Loading recent logs…');
  const loadLogs = async () => {
    try {
      const result = await request(`/api/services/${encodeURIComponent(service.id)}/logs`);
      log.textContent = (result.truncated ? 'Showing the latest excerpt\n' : '') + (result.lines.join('\n') || 'No captured logs.');
    } catch (error) {
      log.textContent = error.message;
    }
  };
  const samples = history.get(service.id) || [];
  if (samples.length) {
    const recent = element('details');
    recent.append(element('summary', 'Recent health results'),
      element('pre', samples.map(entry => `${entry.time}  ${entry.label}`).join('\n')));
    details.append(recent);
  }
  const controls = element('div', null, 'dialog-actions');
  if (service.actions.restart) controls.append(button('Restart', () => { dialog.close(); lifecycle(service, 'restart'); }));
  if (service.actions.force_stop) controls.append(button('Force Stop', () => { dialog.close(); lifecycle(service, 'force'); }, 'error'));
  try {
    const result = await request('/api/registry');
    if (!details.isConnected) return;
    const config = registryEntries(result.registry).find(item => item.id === service.id);
    if (config) {
      details.append(facts([['Group', config.group], ['Runtime', config.runtime], ['Project directory', config.cwd],
        ['Startup command', config.start], ['Health URL', config.health], ['Required environment', config.env?.join(', ')]]));
      controls.append(button('Edit Service', () => editor(config, true)));
      controls.append(button('Remove', async () => {
        if (!await confirmAction('Remove service', `Remove ${service.name} from the registry? Its project and files stay in place.`, 'Remove')) return;
        try {
          await request('/api/registry', {operation: 'remove', id: service.id});
          notice(`Removed ${service.name}`);
          await refresh();
        } catch (error) { notice(error.message, true); }
      }));
    }
  } catch (error) { details.append(element('p', error.message, 'error')); }
  if (!details.isConnected) return;
  const logs = element('details');
  logs.append(element('summary', 'Recent logs'), log, button('Refresh logs', loadLogs));
  logs.addEventListener('toggle', () => { if (logs.open) loadLogs(); });
  details.append(logs, controls);
}

function editor(initial = {}, editing = false, hint = '') {
  showDialog(editing ? 'Edit service' : 'Add service');
  panel.replaceChildren($('editor-template').content.cloneNode(true));
  $('dialog-title').textContent = editing ? 'Edit service' : 'Add service';
  $('editor-hint').textContent = hint;
  $('editor-hint').hidden = !hint;
  for (const close of panel.querySelectorAll('[data-close]')) close.addEventListener('click', () => dialog.close());
  const form = $('editor');
  const fields = form.elements;
  const id = fields.namedItem('id');
  const name = fields.namedItem('name');
  const start = fields.namedItem('start');
  const review = fields.namedItem('review');
  const error = form.querySelector('.form-error');
  for (const input of fields) {
    if (!input.name || input.name === 'review') continue;
    const value = initial[input.name];
    if (input.type === 'checkbox') input.checked = value ?? input.name === 'enabled';
    else if (value != null) input.value = Array.isArray(value) ? value.join(', ') : value;
  }
  $('groups').replaceChildren(...[...new Set(current.filter(item => item.managed).map(item => item.group))]
    .sort().map(group => new Option(group)));
  id.readOnly = editing;
  let manualId = Boolean(initial.id);
  id.addEventListener('input', () => { manualId = true; });
  name.addEventListener('input', () => {
    if (!manualId) id.value = name.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);
  });
  const reviewState = () => {
    const required = Boolean(start.value.trim()) && (!editing || initial.start !== start.value.trim() ||
      (initial.cwd || '') !== fields.namedItem('cwd').value.trim());
    $('review').hidden = !required;
    review.required = required;
  };
  for (const input of [start, fields.namedItem('cwd')]) input.addEventListener('input', reviewState);
  reviewState();
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const save = form.querySelector('button[type="submit"], button:not([type])');
    save.disabled = true;
    const config = {};
    for (const input of fields) {
      if (!input.name || input.name === 'review') continue;
      const value = input.value.trim();
      if (input.type === 'checkbox') config[input.name] = input.checked;
      else if (input.name === 'env') config.env = value ? value.split(',').map(item => item.trim()).filter(Boolean) : [];
      else if (input.type === 'number') config[input.name] = value ? Number(value) : null;
      else config[input.name] = value || null;
    }
    try {
      await request('/api/registry', {operation: editing ? 'edit' : 'add', id: config.id, service: config});
      dialog.close();
      notice(`Saved ${config.name}`);
      switchView('services');
      await refresh();
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      save.disabled = false;
    }
  });
  name.focus();
}

function listenerRow(service) {
  const row = element('li', null, 'discovery-row');
  const name = element('div');
  name.append(element('strong', service.name),
    element('small', `:${service.port} · PID ${service.pid}${service.known_label ? ` · ${service.known_label}` : ''}`));
  row.append(name, button('Inspect', () => listenerDetails(service)));
  return row;
}

async function listenerDetails(service) {
  showDialog(service.name);
  const info = element('div');
  info.append(facts([['Port', service.port], ['PID', service.pid], ['Executable', service.command],
    ['Parent PID', service.parent_pid], ['Bind address', service.address], ['Owning user', service.user]]));
  panel.append(info);
  let evidence = {};
  try {
    evidence = (await request(`/api/discovery/processes/${service.pid}`)).receipt;
    info.append(facts([['Working directory', evidence.cwd], ['Git root', evidence.repository],
      ['Process started', evidence.process_started], ['Evidence', evidence.confidence]]));
  } catch (error) {
    info.append(element('p', error.message, 'error'));
  }
  const name = evidence.repository?.split('/').pop() || service.name;
  info.append(button('Register listener', () => editor({
    id: `service-${service.port}`, name, cwd: evidence.cwd || '', port: service.port,
    enabled: false,
  }, false, 'Review these suggestions before saving. Yard will show this listener as external.')));
}

$('discover-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = $('discover-message');
  const submit = event.target.querySelector('button');
  submit.disabled = true;
  message.hidden = false;
  message.textContent = 'Scanning selected directory…';
  try {
    const answer = await request('/api/discovery/projects', {root: $('root').value});
    const rows = answer.receipt.map(project => {
      const row = element('li', null, 'discovery-row');
      const description = element('div');
      description.append(element('strong', project.name), element('small', `${project.cwd} · ${project.evidence}`));
      row.append(description, button('Register', () => editor({name: project.name, cwd: project.cwd,
        runtime: project.runtime, start: project.start}, false, 'Review the manifest and startup command before saving.')));
      return row;
    });
    $('projects').replaceChildren(...rows);
    message.textContent = rows.length ? `${rows.length} project suggestions` : 'No supported project manifests found.';
  } catch (error) {
    $('projects').replaceChildren();
    message.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

async function manageRegistry() {
  showDialog('Service registry');
  const field = element('textarea');
  field.setAttribute('aria-label', 'Registry JSON to import');
  field.placeholder = 'Paste registry JSON to validate or import';
  const message = element('p');
  message.setAttribute('role', 'status');
  const controls = element('div', null, 'dialog-actions');
  const load = element('input');
  load.type = 'file';
  load.accept = '.json,application/json';
  load.setAttribute('aria-label', 'Choose registry JSON');
  load.addEventListener('change', async () => {
    const [file] = load.files;
    if (file?.size <= 240000) field.value = await file.text();
    else if (file) message.textContent = 'Choose a JSON file no larger than 240 KB.';
  });
  const review = element('input');
  review.type = 'checkbox';
  const agreement = element('label', null, 'check');
  agreement.append(review, document.createTextNode('I reviewed the imported startup commands.'));
  for (const operation of ['validate', 'import']) {
    controls.append(button(operation === 'validate' ? 'Validate JSON' : 'Import services', async () => {
      try {
        if (operation === 'import' && !review.checked) throw new Error('Review the imported startup commands first.');
        await request('/api/registry', {operation, registry: JSON.parse(field.value)});
        message.textContent = operation === 'validate' ? 'Registry JSON is valid.' : 'Services imported.';
        if (operation === 'import') await refresh();
      } catch (error) { message.textContent = error.message; }
    }));
  }
  controls.append(button('Export registry', async () => {
    try {
      const {registry} = await request('/api/registry');
      const url = URL.createObjectURL(new Blob([JSON.stringify(registry, null, 2) + '\n'], {type: 'application/json'}));
      const download = element('a');
      download.href = url;
      download.download = 'yard.config.json';
      download.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { message.textContent = error.message; }
  }));
  panel.append(element('p', 'Import adds services from a JSON registry. IDs and ports must be unique.'), field, load, agreement, message, controls);
}

$('add').addEventListener('click', () => editor());
$('refresh').addEventListener('click', refresh);
$('registry').addEventListener('click', manageRegistry);
$('services-tab').addEventListener('click', () => switchView('services'));
$('discovery-tab').addEventListener('click', () => switchView('discovery'));
for (const control of ['status', 'group', 'sort']) $(control).addEventListener('change', render);
$('search').addEventListener('input', render);
for (const metric of document.querySelectorAll('[data-status]')) {
  metric.addEventListener('click', () => {
    $('status').value = $('status').value === metric.dataset.status ? '' : metric.dataset.status;
    switchView('services');
    render();
  });
}
setInterval(() => { if (!document.hidden && !busy.size) refresh(); }, 4000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
refresh();
