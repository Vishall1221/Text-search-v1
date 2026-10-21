const form = document.querySelector('#search-form');
const input = document.querySelector('#query');
const status = document.querySelector('#status');
const results = document.querySelector('#results');
const dialog = document.querySelector('#player-dialog');
const player = document.querySelector('#player');
const playerMessage = document.querySelector('#player-message');

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function sceneLabel(scene) {
  return `${scene.start_time || secondsLabel(scene.start_seconds)} – ${scene.end_time || secondsLabel(scene.end_seconds)}`;
}

function secondsLabel(value) {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  return `${String(Math.floor(total / 3600)).padStart(2, '0')}:${String(Math.floor(total % 3600 / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

async function openPlayer(movie, scene) {
  document.querySelector('#player-title').textContent = movie.title;
  document.querySelector('#player-time').textContent = `Scene ${sceneLabel(scene)}`;
  playerMessage.textContent = 'Loading video from the movie’s GCS URI…';
  dialog.showModal();
  try {
    const response = await fetch(scene.playback_url, { headers: { Range: 'bytes=0-0' } });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || `Video request failed (${response.status})`);
    }
    if (!dialog.open) return;
    player.src = scene.playback_url;
    player.onloadedmetadata = () => {
      player.currentTime = scene.start_seconds;
      playerMessage.textContent = '';
    };
    player.onerror = () => { playerMessage.textContent = 'Video streaming failed after connecting to GCS.'; };
    player.play().catch(() => {});
  } catch (error) {
    if (dialog.open) playerMessage.textContent = error.message;
  }
}

function renderMovie(movie) {
  const article = el('article', 'movie');
  let poster;
  if (movie.thumbnail_image_url) {
    poster = el('img', 'poster');
    poster.src = movie.thumbnail_image_url;
    poster.alt = `${movie.title} poster`;
    poster.onerror = () => poster.replaceWith(el('div', 'poster poster-fallback', movie.title.slice(0, 1)));
  } else {
    poster = el('div', 'poster poster-fallback', movie.title.slice(0, 1));
  }
  article.append(poster);

  const body = el('div');
  const top = el('div', 'movie-top');
  top.append(el('h2', '', movie.title), el('span', 'score', `${Math.round(movie.match_score * 100)}% match`));
  body.append(top);
  body.append(el('div', 'meta', [movie.primary_language, (movie.genres || []).join(' · '), (movie.cast || []).slice(0, 3).join(', ')].filter(Boolean).join('  •  ')));
  body.append(el('div', 'reason', movie.matched_by));
  if (movie.description) body.append(el('p', 'description', movie.description));

  if (movie.matched_scenes?.length) {
    body.append(el('h3', 'scene-heading', movie.matched_scene_count ? 'Matching scenes' : 'Scenes'));
    const list = el('div', 'scene-list');
    for (const scene of movie.matched_scenes) {
      const row = el('div', 'scene');
      const copy = el('div', 'scene-copy');
      copy.append(el('div', 'scene-time', sceneLabel(scene)));
      copy.append(el('div', 'scene-summary', scene.description || scene.visual_summary || scene.master_scene_summary || 'Scene details unavailable'));
      const button = el('button', '', 'Try video');
      button.type = 'button';
      button.addEventListener('click', () => openPlayer(movie, scene));
      row.append(copy, button);
      list.append(row);
    }
    body.append(list);
  }
  body.append(el('div', 'gcs', `Source: ${movie.movie_gcs_path}`));
  article.append(body);
  return article;
}

async function search(query) {
  input.value = query;
  status.textContent = 'Searching catalog and scenes…';
  results.replaceChildren();
  const submit = form.querySelector('button[type=submit]');
  submit.disabled = true;
  try {
    const response = await fetch('/api/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit: 8 }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Search failed (${response.status})`);
    status.textContent = `${data.total_results} ${data.total_results === 1 ? 'movie' : 'movies'} found · ${data.elapsed_ms} ms · ${data.route.replaceAll('_', ' ')}`;
    if (!data.matched_titles.length) {
      results.append(el('div', 'empty', 'No matching movie or scene in this catalog. Try a title, actor, genre, or a different scene description.'));
    } else {
      for (const movie of data.matched_titles) results.append(renderMovie(movie));
    }
  } catch (error) {
    status.textContent = error.message;
    results.append(el('div', 'empty', 'Search could not run. Check that PostgreSQL and the local API are running.'));
  } finally {
    submit.disabled = false;
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (query) search(query);
});
for (const button of document.querySelectorAll('[data-query]')) {
  button.addEventListener('click', () => search(button.dataset.query));
}
document.querySelector('#player-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => { player.pause(); player.removeAttribute('src'); player.load(); });
