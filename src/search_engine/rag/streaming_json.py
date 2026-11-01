"""Decode only the top-level JSON answer string while provider bytes arrive.

Incomplete escapes and surrogate pairs are held until complete. Status, citation
arrays and JSON syntax are never emitted as assistant text. The entire document
still requires final schema/citation validation before it can be persisted.
"""
import json


class AnswerJsonDecoder:
    def __init__(self) -> None:
        self.raw = ''
        self.answer = ''
        self._position = 0
        self._stage = 'start'
        self._key = None
        self._seen_answer = False

    def feed(self, fragment: str) -> str:
        self.raw += fragment
        output = []
        decoder = json.JSONDecoder()
        while self._position < len(self.raw):
            position = self._position
            char = self.raw[position]
            if self._stage != 'answer' and char.isspace():
                self._position += 1
                continue
            if self._stage == 'start':
                if char != '{':
                    raise ValueError('Expected a JSON object')
                self._stage = 'key'
            elif self._stage == 'key':
                if char == '}':
                    self._stage = 'closed'
                else:
                    try:
                        key, end = decoder.raw_decode(self.raw, position)
                    except json.JSONDecodeError:
                        break
                    if not isinstance(key, str):
                        raise ValueError('Expected a JSON key')
                    self._key = key
                    self._position = end
                    self._stage = 'colon'
                    continue
            elif self._stage == 'colon':
                if char != ':':
                    raise ValueError('Expected colon')
                self._stage = 'value'
            elif self._stage == 'value':
                if self._key == 'answer':
                    if char != '"' or self._seen_answer:
                        raise ValueError('Expected one answer string')
                    self._seen_answer = True
                    self._stage = 'answer'
                else:
                    try:
                        _, end = decoder.raw_decode(self.raw, position)
                    except json.JSONDecodeError:
                        break
                    self._position = end
                    self._stage = 'separator'
                    continue
            elif self._stage == 'answer':
                if char == '"':
                    self._stage = 'separator'
                elif char == '\\':
                    if position + 1 >= len(self.raw):
                        break
                    length = 6 if self.raw[position+1] == 'u' else 2
                    if position + length > len(self.raw):
                        break
                    escape = self.raw[position:position+length]
                    if length == 6:
                        code = int(escape[2:], 16)
                        if 0xD800 <= code <= 0xDBFF:
                            if position+12 > len(self.raw):
                                break
                            escape = self.raw[position:position+12]
                            if escape[6:8] != '\\u' or not 0xDC00 <= int(escape[8:], 16) <= 0xDFFF:
                                raise ValueError('Invalid surrogate pair')
                            length = 12
                        elif 0xDC00 <= code <= 0xDFFF:
                            raise ValueError('Unpaired surrogate')
                    output.append(json.loads('"'+escape+'"'))
                    self._position += length
                    continue
                elif ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF:
                    raise ValueError('Invalid JSON string character')
                else:
                    output.append(char)
            elif self._stage == 'separator':
                if char == ',':
                    self._stage = 'key'
                elif char == '}':
                    self._stage = 'closed'
                else:
                    raise ValueError('Expected separator')
            elif self._stage == 'closed':
                # Providers may finish a JSON object before the final whitespace
                # fragment. Accept that valid tail without treating it as content.
                if char.isspace():
                    self._position += 1
                    continue
                raise ValueError('Unexpected trailing JSON content')
            else:
                raise ValueError('Unexpected trailing JSON content')
            self._position += 1
        delta = ''.join(output)
        self.answer += delta
        return delta
