import { createRoot } from 'react-dom/client'
import './AppDialog.css'

function openDialog(title, initialValue) {
  return new Promise((resolve) => {
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    const previousFocus = document.activeElement
    const finish = (value) => {
      root.unmount()
      host.remove()
      previousFocus?.focus()
      resolve(value)
    }
    root.render(
      <dialog className="app-dialog" ref={(node) => node?.showModal()} onCancel={(event) => { event.preventDefault(); finish(null) }}>
        <form onSubmit={(event) => { event.preventDefault(); finish(initialValue === undefined ? true : new FormData(event.currentTarget).get('value')) }}>
          <h2>{title}</h2>
          {initialValue !== undefined ? <input autoFocus name="value" defaultValue={initialValue} required aria-label="New name" /> : <p>This action cannot be undone.</p>}
          <footer><button type="button" onClick={() => finish(null)}>Cancel</button><button autoFocus={initialValue === undefined} type="submit">{initialValue === undefined ? 'Confirm' : 'Save'}</button></footer>
        </form>
      </dialog>,
    )
  })
}

export const confirmAction = (title) => openDialog(title)
export const promptValue = (title, value) => openDialog(title, value)
