import React, { useState } from 'react';
import { MANIFEST_NAMES, uploadManifest } from '../api';
import { errorMessages, pathText } from '../format';
import Icon from './Icon';

export default function ManifestUpload({ components, onImported }) {
  const [componentId, setComponentId] = useState('');
  const [result, setResult] = useState(null);
  const [errors, setErrors] = useState([]);
  const [uploading, setUploading] = useState(false);

  async function upload(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setResult(null);
    if (!MANIFEST_NAMES.test(file.name)) {
      setErrors([`"${file.name}" isn't a requirements.txt or package.json file.`]);
      return;
    }
    setErrors([]);
    setUploading(true);
    try {
      const data = await uploadManifest(componentId, file);
      setResult({ ...data, fileName: file.name });
      if (onImported) onImported(data);
    } catch (error) {
      setErrors(errorMessages(error));
    } finally {
      setUploading(false);
    }
  }

  const chosen = components.find(component => String(component.id) === String(componentId));
  return (
    <section className="card">
      <h3>Import dependencies</h3>
      <p className="muted small">Upload a requirements.txt or package.json. Packages that match a component (by name or
        package name) become dependencies; the rest are listed so you can check them.</p>
      <div className="form-row">
        <label>Component
          <select value={componentId} onChange={event => { setComponentId(event.target.value); setResult(null); setErrors([]); }}>
            <option value="">Choose a component</option>
            {components.map(component => <option key={component.id} value={component.id}>{component.name}</option>)}
          </select>
        </label>
        <label className={`file-pick ${componentId ? '' : 'disabled'}`}>Manifest file
          <input type="file" accept=".txt,.in,.json,application/json,text/plain" onChange={upload}
                 disabled={!componentId || uploading} aria-label="Manifest file" />
          <span className="button secondary"><Icon name="upload" />{uploading ? 'Uploading...' : 'Choose file'}</span>
        </label>
      </div>
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
      {result && (
        <div className="manifest-result" aria-live="polite">
          <p><strong>{result.fileName}</strong> for {chosen?.name}: {result.packages} package{result.packages === 1 ? '' : 's'} read.</p>
          <dl className="kv">
            <dt>New dependencies</dt><dd>{result.created.length ? result.created.join(', ') : 'none'}</dd>
            <dt>Already linked</dt><dd>{result.existing.length ? result.existing.join(', ') : 'none'}</dd>
            <dt>No matching component</dt>
            <dd>{result.unmatched.length ? (
              <span className="tags">{result.unmatched.map(name => <span key={name} className="tag">{name}</span>)}</span>
            ) : 'none'}</dd>
          </dl>
          {result.cycle && <p className="error" role="alert">This created a dependency cycle: {pathText(result.cycle)}</p>}
        </div>
      )}
    </section>
  );
}
