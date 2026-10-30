import './StructuredAnswer.css'

export default function StructuredAnswer({ presentation }) {
  if (!presentation || presentation.type === 'standard') return null

  if (presentation.type === 'comparison') {
    return (
      <div className="structured-answer__table" role="region" aria-label="Comparison" tabIndex="0">
        <table>
          <thead><tr>{presentation.headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead>
          <tbody>
            {presentation.rows.map((row, rowIndex) => (
              <tr key={`${rowIndex}-${row.join('-')}`}>
                {row.map((cell, cellIndex) => <td key={`${cellIndex}-${cell}`}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (presentation.type === 'timeline') {
    return (
      <ol className="structured-answer__timeline" aria-label="Timeline">
        {presentation.items.map((item) => (
          <li key={`${item.label}-${item.text}`}>
            <time>{item.label}</time><span>{item.text}</span>
          </li>
        ))}
      </ol>
    )
  }

  if (presentation.type === 'checklist') {
    return (
      <ul className="structured-answer__checklist" aria-label="Checklist">
        {presentation.items.map((item) => (
          <li key={item.text}>
            <input type="checkbox" checked={Boolean(item.completed)} readOnly aria-label={item.text} />
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <ol className="structured-answer__steps" aria-label="Steps">
      {presentation.items.map((item) => <li key={`${item.label}-${item.text}`}>{item.text}</li>)}
    </ol>
  )
}
