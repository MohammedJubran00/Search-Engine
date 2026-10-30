import assert from 'node:assert/strict'
import test from 'node:test'

import { MAX_DOCUMENT_BYTES, validateDocumentFile } from './documentFiles.js'

test('document file validation accepts 100 MiB and rejects the next byte', () => {
  assert.equal(MAX_DOCUMENT_BYTES, 104857600)
  assert.equal(validateDocumentFile({ name: 'report.pdf', size: MAX_DOCUMENT_BYTES }), '')
  assert.match(
    validateDocumentFile({ name: 'report.pdf', size: MAX_DOCUMENT_BYTES + 1 }),
    /or smaller/,
  )
})

test('document file validation rejects empty and unsupported files', () => {
  assert.match(validateDocumentFile({ name: 'empty.txt', size: 0 }), /empty/)
  assert.match(validateDocumentFile({ name: 'malware.exe', size: 10 }), /PDF, DOCX, or TXT/)
})
