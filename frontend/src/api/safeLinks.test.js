import assert from 'node:assert/strict'
import test from 'node:test'

import { isSafeHref } from './safeLinks.js'

test('link safety accepts navigable web links and rejects executable schemes', () => {
  assert.equal(isSafeHref('https://example.com/report'), true)
  assert.equal(isSafeHref('/local-reference'), true)
  assert.equal(isSafeHref('mailto:owner@example.com'), true)
  assert.equal(isSafeHref('javascript:alert(1)'), false)
  assert.equal(isSafeHref('data:text/html,<script>alert(1)</script>'), false)
})
