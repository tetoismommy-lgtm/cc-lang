import sys
import random
import time
import math
import os
import json
import urllib.request
import urllib.error
import urllib.parse
import atexit

sys.stdout.reconfigure(encoding='utf-8')

# --- READLINE (cross-platform) ---
try:
    import readline
    HAS_READLINE = True
except ImportError:
    try:
        import pyreadline3 as readline
        HAS_READLINE = True
    except ImportError:
        HAS_READLINE = False

# --- LEXER ---

KEYWORDS = [
    "SPEAK", "GRANT", "TO", "OBEY", "ALSO", "OTHERWISE", "CONTRACT",
    "IMMORTAL", "SILENCE", "BETRAY", "END", "REPEAT", "ASK",
    "WHILE", "GATHER", "ADD", "GET", "LENGTH", "JOIN", "SLICE",
    "WRITE", "READ", "INVOKE", "REMOVE", "SIZE", "INTO",
    "STOP", "WITH", "RETURN", "ORD", "CHR", "MOD",
    "FETCH", "POST", "PUT", "DELETE", "OR", "FAIL", "CONTINUE",
    "PARSE", "PLUCK", "HEADER", "BEARER", "BASIC", "SHOW",
    "PRETTY", "ENV", "DOTENV"
]

def lex(source):
    tokens = []
    i = 0

    while i < len(source):
        char = source[i]

        if char in ' \r\t':
            i += 1

        elif char == '\n':
            tokens.append(("NEWLINE", "\n"))
            i += 1

        elif source[i:i+7] == "SILENCE":
            while i < len(source) and source[i] != '\n':
                i += 1

        elif char.isalpha() or char == '_':
            word = ""
            while i < len(source) and (source[i].isalpha() or source[i] == '_'):
                word += source[i]
                i += 1
            if word in KEYWORDS:
                tokens.append(("KEYWORD", word))
            else:
                tokens.append(("NAME", word))

        elif char == '"':
            string = ""
            i += 1
            while i < len(source) and source[i] != '"':
                if source[i] == '\\' and i + 1 < len(source):
                    nxt = source[i + 1]
                    if nxt == 'n':   string += '\n'
                    elif nxt == 't': string += '\t'
                    elif nxt == '"': string += '"'
                    else:            string += nxt
                    i += 2
                else:
                    string += source[i]
                    i += 1
            i += 1
            tokens.append(("STRING", string))

        elif char.isdigit():
            number = ""
            while i < len(source) and (source[i].isdigit() or source[i] == '.'):
                number += source[i]
                i += 1
            tokens.append(("NUMBER", number))

        elif char in '+-*/':
            tokens.append(("OP", char))
            i += 1

        elif char == '>' and i+1 < len(source) and source[i+1] == '=':
            tokens.append(("CMP", ">=")); i += 2
        elif char == '<' and i+1 < len(source) and source[i+1] == '=':
            tokens.append(("CMP", "<=")); i += 2
        elif char == '>':
            tokens.append(("CMP", ">")); i += 1
        elif char == '<':
            tokens.append(("CMP", "<")); i += 1
        elif char == '=' and i+1 < len(source) and source[i+1] == '=':
            tokens.append(("CMP", "==")); i += 2
        elif char == '!' and i+1 < len(source) and source[i+1] == '=':
            tokens.append(("CMP", "!=")); i += 2

        else:
            i += 1

    return tokens


# --- EXPRESSIONS ---

def evaluate(expr, memory):
    values = []
    ops = []

    for token in expr:
        kind, val = token
        if kind == "NUMBER":
            values.append(float(val) if '.' in val else int(val))
        elif kind == "NAME":
            if val not in memory:
                raise Exception(f"CC does not recognize '{val}' — it was never granted.")
            values.append(memory[val])
        elif kind == "STRING":
            values.append(val)
        elif kind == "OP":
            ops.append(val)

    if not values:
        raise Exception("CC cannot evaluate an empty expression.")

    result = values[0]
    for i, op in enumerate(ops):
        if i + 1 >= len(values):
            break
        if op == "+":   result += values[i + 1]
        elif op == "-": result -= values[i + 1]
        elif op == "*": result *= values[i + 1]
        elif op == "/":
            if values[i + 1] == 0:
                raise Exception("CC refuses to divide by zero.")
            result /= values[i + 1]

    return result


def compare(left, cmp, right):
    try:
        if cmp == ">":  return left > right
        if cmp == "<":  return left < right
        if cmp == ">=": return left >= right
        if cmp == "<=": return left <= right
        if cmp == "==": return str(left) == str(right)
        if cmp == "!=": return str(left) != str(right)
    except TypeError:
        raise Exception(f"CC cannot compare '{left}' and '{right}' — mismatched types.")
    return False


# --- SIGNALS ---

class StopSignal(Exception):
    pass

class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


# --- HTTP HELPERS ---

def make_request(method, url, path, headers_list, body, on_fail, memory):
    full_url = url.rstrip("/") + ("/" + path.lstrip("/") if path else "")
    headers = {}

    if headers_list and headers_list in memory:
        hlist = memory[headers_list]
        if isinstance(hlist, list):
            for h in hlist:
                if ":" in str(h):
                    k, v = str(h).split(":", 1)
                    headers[k.strip()] = v.strip()

    try:
        data = None
        if body:
            data = body.encode("utf-8")
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"

        req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            body_text = resp.read().decode("utf-8", errors="replace")
            memory["response_status"] = resp.status
            memory["response_body"]   = body_text
            memory["response_error"]  = "none"
            memory["response_headers"] = str(dict(resp.headers))

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        memory["response_status"]  = e.code
        memory["response_body"]    = err_body
        memory["response_error"]   = f"{e.code} {e.reason}"
        memory["response_headers"] = ""
        if on_fail == "FAIL":
            raise Exception(f"HTTP {e.code} {e.reason} — {full_url}")

    except urllib.error.URLError as e:
        memory["response_status"]  = 0
        memory["response_body"]    = ""
        memory["response_error"]   = str(e.reason)
        memory["response_headers"] = ""
        if on_fail == "FAIL":
            raise Exception(f"Network error — {e.reason}")

    except Exception as e:
        memory["response_status"]  = 0
        memory["response_body"]    = ""
        memory["response_error"]   = str(e)
        memory["response_headers"] = ""
        if on_fail == "FAIL":
            raise Exception(f"Request failed — {e}")


# --- ENV / DOTENV HELPERS ---

def load_dotenv(filepath, memory):
    """Parse a .env file and load keys into memory."""
    if not os.path.exists(filepath):
        raise Exception(f"CC cannot find env file '{filepath}'.")
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip()
                # strip optional surrounding quotes
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                memory[key.lower()] = val


# --- PARSER ---

def collect_block(tokens, i):
    body_tokens = []
    depth = 0
    block_starters = [
        ("KEYWORD", "OBEY"), ("KEYWORD", "REPEAT"),
        ("KEYWORD", "CONTRACT"), ("KEYWORD", "WHILE")
    ]
    while i < len(tokens):
        t = tokens[i]
        if t in block_starters:
            depth += 1
        if t == ("KEYWORD", "END") and depth == 0:
            i += 1
            break
        if t == ("KEYWORD", "END") and depth > 0:
            depth -= 1
        body_tokens.append(t)
        i += 1
    return body_tokens, i


def parse_single_expr(tokens, i):
    expr = []
    if i < len(tokens) and tokens[i][0] in ("NUMBER", "NAME", "STRING"):
        expr.append(tokens[i])
        i += 1
    return expr, i


def parse_index_expr(tokens, i):
    expr = []
    if i < len(tokens) and tokens[i][0] in ("NUMBER", "NAME"):
        expr.append(tokens[i])
        i += 1
    if i < len(tokens) and tokens[i][0] == "OP" and tokens[i][1] in ("+", "-"):
        expr.append(tokens[i])
        i += 1
        if i < len(tokens) and tokens[i][0] in ("NUMBER", "NAME"):
            expr.append(tokens[i])
            i += 1
    return expr, i


def parse_expr(tokens, i):
    expr = []
    while i < len(tokens) and tokens[i][0] in ("NUMBER", "NAME", "STRING", "OP"):
        expr.append(tokens[i])
        i += 1
    return expr, i


def parse_speak_expr(tokens, i):
    expr = []
    if i >= len(tokens):
        return expr, i
    if tokens[i][0] in ("NUMBER", "NAME", "STRING"):
        expr.append(tokens[i])
        i += 1
    while i < len(tokens) and tokens[i][0] == "OP":
        expr.append(tokens[i])
        i += 1
        if i < len(tokens) and tokens[i][0] in ("NUMBER", "NAME"):
            expr.append(tokens[i])
            i += 1
    return expr, i


def parse(tokens):
    tokens = [t for t in tokens if t[0] != "NEWLINE"]
    instructions = []
    i = 0

    while i < len(tokens):
        token = tokens[i]

        # SPEAK
        if token == ("KEYWORD", "SPEAK"):
            i += 1
            expr, i = parse_speak_expr(tokens, i)
            instructions.append(("SPEAK", expr))

        # GRANT
        elif token == ("KEYWORD", "GRANT"):
            name = tokens[i + 1][1]
            i += 3
            expr, i = parse_expr(tokens, i)
            instructions.append(("GRANT", name, expr, False))

        # IMMORTAL
        elif token == ("KEYWORD", "IMMORTAL"):
            name = tokens[i + 1][1]
            i += 3
            expr, i = parse_expr(tokens, i)
            instructions.append(("GRANT", name, expr, True))

        # OBEY
        elif token == ("KEYWORD", "OBEY"):
            i += 1
            left, i = parse_single_expr(tokens, i)
            cmp = tokens[i][1]
            i += 1
            right, i = parse_single_expr(tokens, i)

            branches = []
            otherwise_tokens = []
            current_body = []
            current_left = left
            current_cmp = cmp
            current_right = right
            in_otherwise = False
            depth = 0
            block_starters = [
                ("KEYWORD", "OBEY"), ("KEYWORD", "REPEAT"),
                ("KEYWORD", "CONTRACT"), ("KEYWORD", "WHILE")
            ]

            while i < len(tokens):
                t = tokens[i]
                if t in block_starters:
                    depth += 1
                    (otherwise_tokens if in_otherwise else current_body).append(t)
                    i += 1
                    continue
                if t == ("KEYWORD", "END") and depth > 0:
                    depth -= 1
                    (otherwise_tokens if in_otherwise else current_body).append(t)
                    i += 1
                    continue
                if t == ("KEYWORD", "END") and depth == 0:
                    i += 1
                    break
                if t == ("KEYWORD", "ALSO") and depth == 0:
                    branches.append((current_left, current_cmp, current_right, current_body))
                    current_body = []
                    i += 2
                    current_left, i = parse_single_expr(tokens, i)
                    current_cmp = tokens[i][1]
                    i += 1
                    current_right, i = parse_single_expr(tokens, i)
                    continue
                if t == ("KEYWORD", "OTHERWISE") and depth == 0:
                    branches.append((current_left, current_cmp, current_right, current_body))
                    current_body = []
                    in_otherwise = True
                    i += 1
                    continue
                if in_otherwise:
                    otherwise_tokens.append(t)
                else:
                    current_body.append(t)
                i += 1

            if not in_otherwise:
                branches.append((current_left, current_cmp, current_right, current_body))

            parsed_branches = [(l, c, r, parse(b)) for l, c, r, b in branches]
            parsed_otherwise = parse(otherwise_tokens)
            instructions.append(("OBEY", parsed_branches, parsed_otherwise))

        # WHILE
        elif token == ("KEYWORD", "WHILE"):
            i += 1
            left, i = parse_single_expr(tokens, i)
            cmp = tokens[i][1]
            i += 1
            right, i = parse_single_expr(tokens, i)
            body_tokens, i = collect_block(tokens, i)
            body = parse(body_tokens)
            instructions.append(("WHILE", left, cmp, right, body))

        # REPEAT
        elif token == ("KEYWORD", "REPEAT"):
            i += 1
            times = tokens[i]
            i += 1
            body_tokens, i = collect_block(tokens, i)
            body = parse(body_tokens)
            instructions.append(("REPEAT", times, body))

        # CONTRACT
        elif token == ("KEYWORD", "CONTRACT"):
            i += 1
            name = tokens[i][1]
            i += 1
            params = []
            if i < len(tokens) and tokens[i] == ("KEYWORD", "WITH"):
                i += 1
                while i < len(tokens) and tokens[i][0] == "NAME":
                    params.append(tokens[i][1])
                    i += 1
            body_tokens, i = collect_block(tokens, i)
            body = parse(body_tokens)
            instructions.append(("CONTRACT", name, params, body))

        # ASK
        elif token == ("KEYWORD", "ASK"):
            i += 1
            name = tokens[i][1]
            i += 1
            prompt = tokens[i][1]
            i += 1
            instructions.append(("ASK", name, prompt))

        # BETRAY
        elif token == ("KEYWORD", "BETRAY"):
            i += 1
            msg = tokens[i][1]
            i += 1
            instructions.append(("BETRAY", msg))

        # STOP
        elif token == ("KEYWORD", "STOP"):
            instructions.append(("STOP",))
            i += 1

        # RETURN
        elif token == ("KEYWORD", "RETURN"):
            i += 1
            expr, i = parse_expr(tokens, i)
            instructions.append(("RETURN", expr))

        # GATHER
        elif token == ("KEYWORD", "GATHER"):
            i += 1
            name = tokens[i][1]
            i += 1
            instructions.append(("GATHER", name))

        # ADD
        elif token == ("KEYWORD", "ADD"):
            i += 1
            name = tokens[i][1]
            i += 1
            expr, i = parse_expr(tokens, i)
            instructions.append(("ADD", name, expr))

        # REMOVE
        elif token == ("KEYWORD", "REMOVE"):
            i += 1
            name = tokens[i][1]
            i += 1
            expr, i = parse_single_expr(tokens, i)
            instructions.append(("REMOVE", name, expr))

        # GET
        elif token == ("KEYWORD", "GET"):
            i += 1
            listname = tokens[i][1]
            i += 1
            expr, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            varname = tokens[i][1]
            i += 1
            instructions.append(("GET", listname, expr, varname))

        # SIZE
        elif token == ("KEYWORD", "SIZE"):
            i += 1
            listname = tokens[i][1]
            i += 1  # skip INTO
            i += 1
            varname = tokens[i][1]
            i += 1
            instructions.append(("SIZE", listname, varname))

        # LENGTH
        elif token == ("KEYWORD", "LENGTH"):
            i += 1
            name = tokens[i][1]
            i += 1  # skip INTO
            i += 1
            result = tokens[i][1]
            i += 1
            instructions.append(("LENGTH", name, result))

        # JOIN
        elif token == ("KEYWORD", "JOIN"):
            i += 1
            a = tokens[i][1]
            i += 1
            b = tokens[i][1]
            i += 1  # skip INTO
            i += 1
            result = tokens[i][1]
            i += 1
            instructions.append(("JOIN", a, b, result))

        # SLICE
        elif token == ("KEYWORD", "SLICE"):
            i += 1
            name = tokens[i][1]
            i += 1
            start_expr, i = parse_index_expr(tokens, i)
            end_expr,   i = parse_index_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("SLICE", name, start_expr, end_expr, result))

        # WRITE
        elif token == ("KEYWORD", "WRITE"):
            i += 1
            filename_expr, i = parse_single_expr(tokens, i)
            content_expr,  i = parse_speak_expr(tokens, i)
            instructions.append(("WRITE", filename_expr, content_expr))

        # READ
        elif token == ("KEYWORD", "READ"):
            i += 1
            filename_expr, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            varname = tokens[i][1]
            i += 1
            instructions.append(("READ", filename_expr, varname))

        # INVOKE
        elif token == ("KEYWORD", "INVOKE"):
            i += 1
            module = tokens[i][1]
            i += 1
            instructions.append(("INVOKE", module))

        # ORD
        elif token == ("KEYWORD", "ORD"):
            i += 1
            src = tokens[i]
            i += 1
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("ORD", src, result))

        # CHR
        elif token == ("KEYWORD", "CHR"):
            i += 1
            expr, i = parse_index_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("CHR", expr, result))

        # MOD
        elif token == ("KEYWORD", "MOD"):
            i += 1
            a_expr, i = parse_index_expr(tokens, i)
            b_expr, i = parse_index_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("MOD", a_expr, b_expr, result))

        # FETCH
        elif token == ("KEYWORD", "FETCH"):
            i += 1
            url_expr,  i = parse_single_expr(tokens, i)
            path_expr, i = parse_single_expr(tokens, i)
            headers_var = None
            if i < len(tokens) and tokens[i][0] == "NAME" and tokens[i] != ("KEYWORD", "INTO"):
                headers_var = tokens[i][1]
                i += 1
            i += 1  # skip INTO
            resp_var = tokens[i][1]
            i += 1
            on_fail = "FAIL"
            if i < len(tokens) and tokens[i] == ("KEYWORD", "OR"):
                i += 1
                on_fail = tokens[i][1]
                i += 1
            instructions.append(("FETCH", url_expr, path_expr, headers_var, resp_var, on_fail))

        # POST
        elif token == ("KEYWORD", "POST"):
            i += 1
            url_expr,  i = parse_single_expr(tokens, i)
            path_expr, i = parse_single_expr(tokens, i)
            body_expr, i = parse_single_expr(tokens, i)
            headers_var = None
            if i < len(tokens) and tokens[i][0] == "NAME" and tokens[i] != ("KEYWORD", "INTO"):
                headers_var = tokens[i][1]
                i += 1
            i += 1  # skip INTO
            resp_var = tokens[i][1]
            i += 1
            on_fail = "FAIL"
            if i < len(tokens) and tokens[i] == ("KEYWORD", "OR"):
                i += 1
                on_fail = tokens[i][1]
                i += 1
            instructions.append(("HTTP_METHOD", "POST", url_expr, path_expr, body_expr, headers_var, resp_var, on_fail))

        # PUT
        elif token == ("KEYWORD", "PUT"):
            i += 1
            url_expr,  i = parse_single_expr(tokens, i)
            path_expr, i = parse_single_expr(tokens, i)
            body_expr, i = parse_single_expr(tokens, i)
            headers_var = None
            if i < len(tokens) and tokens[i][0] == "NAME" and tokens[i] != ("KEYWORD", "INTO"):
                headers_var = tokens[i][1]
                i += 1
            i += 1  # skip INTO
            resp_var = tokens[i][1]
            i += 1
            on_fail = "FAIL"
            if i < len(tokens) and tokens[i] == ("KEYWORD", "OR"):
                i += 1
                on_fail = tokens[i][1]
                i += 1
            instructions.append(("HTTP_METHOD", "PUT", url_expr, path_expr, body_expr, headers_var, resp_var, on_fail))

        # DELETE
        elif token == ("KEYWORD", "DELETE"):
            i += 1
            url_expr,  i = parse_single_expr(tokens, i)
            path_expr, i = parse_single_expr(tokens, i)
            headers_var = None
            if i < len(tokens) and tokens[i][0] == "NAME" and tokens[i] != ("KEYWORD", "INTO"):
                headers_var = tokens[i][1]
                i += 1
            i += 1  # skip INTO
            resp_var = tokens[i][1]
            i += 1
            on_fail = "FAIL"
            if i < len(tokens) and tokens[i] == ("KEYWORD", "OR"):
                i += 1
                on_fail = tokens[i][1]
                i += 1
            instructions.append(("HTTP_METHOD", "DELETE", url_expr, path_expr, None, headers_var, resp_var, on_fail))

        # PARSE
        elif token == ("KEYWORD", "PARSE"):
            i += 1
            src, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("PARSE", src, result))

        # PLUCK
        elif token == ("KEYWORD", "PLUCK"):
            i += 1
            data_var = tokens[i][1]
            i += 1
            key, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("PLUCK", data_var, key, result))

        # PRETTY <var>  — pretty print JSON
        elif token == ("KEYWORD", "PRETTY"):
            i += 1
            src, i = parse_single_expr(tokens, i)
            instructions.append(("PRETTY", src))

        # HEADER
        elif token == ("KEYWORD", "HEADER"):
            i += 1
            key, i = parse_single_expr(tokens, i)
            val, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("HEADER", key, val, result))

        # BEARER
        elif token == ("KEYWORD", "BEARER"):
            i += 1
            tok, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("BEARER", tok, result))

        # BASIC
        elif token == ("KEYWORD", "BASIC"):
            i += 1
            user,   i = parse_single_expr(tokens, i)
            passwd, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("BASIC", user, passwd, result))

        # SHOW
        elif token == ("KEYWORD", "SHOW"):
            instructions.append(("SHOW",))
            i += 1

        # ENV <key> INTO <var>  — read a single env variable
        elif token == ("KEYWORD", "ENV"):
            i += 1
            key, i = parse_single_expr(tokens, i)
            i += 1  # skip INTO
            result = tokens[i][1]
            i += 1
            instructions.append(("ENV", key, result))

        # DOTENV <filepath>  — load entire .env file into memory
        elif token == ("KEYWORD", "DOTENV"):
            i += 1
            path, i = parse_single_expr(tokens, i)
            instructions.append(("DOTENV", path))

        # NAME — contract call or module usage
        elif token[0] == "NAME":

            if token[1] == "RANDOM":
                i += 1
                min_expr, i = parse_single_expr(tokens, i)
                max_expr, i = parse_single_expr(tokens, i)
                i += 1  # skip INTO
                varname = tokens[i][1]
                i += 1
                instructions.append(("RANDOM", min_expr, max_expr, varname))

            elif token[1] == "TIME":
                i += 1
                i += 1  # skip INTO
                varname = tokens[i][1]
                i += 1
                instructions.append(("TIME_GET", varname))

            elif token[1] == "MATH":
                i += 1
                func = tokens[i][1]
                i += 1
                expr, i = parse_single_expr(tokens, i)
                i += 1  # skip INTO
                varname = tokens[i][1]
                i += 1
                instructions.append(("MATH", func, expr, varname))

            else:
                name = token[1]
                i += 1
                args = []
                if i < len(tokens) and tokens[i] == ("KEYWORD", "WITH"):
                    i += 1
                    while i < len(tokens) and tokens[i][0] in ("NUMBER", "NAME", "STRING"):
                        args.append([tokens[i]])
                        i += 1
                instructions.append(("CALL", name, args))

        else:
            i += 1

    return instructions


# --- INTERPRETER ---

def interpret(instructions, memory=None):
    if memory is None:
        memory = {}

    if "__constants__" not in memory:
        memory["__constants__"] = set()
    if "__invoked__" not in memory:
        memory["__invoked__"] = set()

    constants = memory["__constants__"]
    invoked   = memory["__invoked__"]

    for instruction in instructions:

        if instruction[0] == "SPEAK":
            expr = instruction[1]
            if len(expr) == 1 and expr[0][0] == "STRING":
                print(expr[0][1])
            else:
                result = evaluate(expr, memory)
                if isinstance(result, float) and result.is_integer():
                    print(int(result))
                else:
                    print(result)

        elif instruction[0] == "GRANT":
            name, expr, is_immortal = instruction[1], instruction[2], instruction[3]
            if name in constants:
                raise Exception(f"CC refuses — '{name}' is IMMORTAL and cannot be changed.")
            if len(expr) == 1 and expr[0][0] == "STRING":
                memory[name] = expr[0][1]
            else:
                memory[name] = evaluate(expr, memory)
            if is_immortal:
                constants.add(name)

        elif instruction[0] == "OBEY":
            branches, otherwise = instruction[1], instruction[2]
            executed = False
            for left, cmp, right, body in branches:
                lval = evaluate(left, memory)
                rval = evaluate(right, memory)
                if compare(lval, cmp, rval):
                    interpret(body, memory)
                    executed = True
                    break
            if not executed:
                interpret(otherwise, memory)

        elif instruction[0] == "WHILE":
            left, cmp, right, body = instruction[1], instruction[2], instruction[3], instruction[4]
            count = 0
            while True:
                lval = evaluate(left, memory)
                rval = evaluate(right, memory)
                if not compare(lval, cmp, rval):
                    break
                try:
                    interpret(body, memory)
                except StopSignal:
                    break
                count += 1
                if count >= 100000:
                    raise Exception("CC grows impatient — infinite loop detected.")

        elif instruction[0] == "REPEAT":
            kind, val = instruction[1]
            times = int(val) if kind == "NUMBER" else memory[val]
            for _ in range(times):
                try:
                    interpret(instruction[2], memory)
                except StopSignal:
                    break

        elif instruction[0] == "CONTRACT":
            name, params, body = instruction[1], instruction[2], instruction[3]
            memory[name] = ("__contract__", params, body)

        elif instruction[0] == "CALL":
            name, args = instruction[1], instruction[2]
            if name not in memory:
                raise Exception(f"CC does not recognize the contract '{name}'.")
            val = memory[name]
            if not (isinstance(val, tuple) and val[0] == "__contract__"):
                raise Exception(f"CC does not recognize the contract '{name}'.")
            _, params, body = val

            if params:
                local = dict(memory)
                for j, param in enumerate(params):
                    if j < len(args):
                        local[param] = evaluate(args[j], memory)
                    else:
                        raise Exception(f"CC expected argument '{param}' but received none.")
                try:
                    interpret(body, local)
                except ReturnSignal as r:
                    memory["__return__"] = r.value
                for k, v in local.items():
                    memory[k] = v
            else:
                try:
                    interpret(body, memory)
                except ReturnSignal as r:
                    memory["__return__"] = r.value

        elif instruction[0] == "ASK":
            name, prompt = instruction[1], instruction[2]
            result = input(prompt + ": ")
            try:
                memory[name] = int(result)
            except ValueError:
                try:
                    memory[name] = float(result)
                except ValueError:
                    memory[name] = result

        elif instruction[0] == "BETRAY":
            raise Exception(f"CC betrays you — {instruction[1]}")

        elif instruction[0] == "STOP":
            raise StopSignal()

        elif instruction[0] == "RETURN":
            expr = instruction[1]
            if len(expr) == 1 and expr[0][0] == "STRING":
                raise ReturnSignal(expr[0][1])
            else:
                raise ReturnSignal(evaluate(expr, memory))

        elif instruction[0] == "GATHER":
            memory[instruction[1]] = []

        elif instruction[0] == "ADD":
            name, expr = instruction[1], instruction[2]
            if name not in memory or not isinstance(memory[name], list):
                raise Exception(f"CC cannot add to '{name}' — it is not a list.")
            if len(expr) == 1 and expr[0][0] == "STRING":
                memory[name].append(expr[0][1])
            else:
                memory[name].append(evaluate(expr, memory))

        elif instruction[0] == "REMOVE":
            name, expr = instruction[1], instruction[2]
            if name not in memory or not isinstance(memory[name], list):
                raise Exception(f"CC cannot remove from '{name}' — it is not a list.")
            idx = int(evaluate(expr, memory))
            if idx < 0 or idx >= len(memory[name]):
                raise Exception(f"CC refuses — index {idx} is out of bounds.")
            memory[name].pop(idx)

        elif instruction[0] == "GET":
            listname, expr, varname = instruction[1], instruction[2], instruction[3]
            if listname not in memory or not isinstance(memory[listname], list):
                raise Exception(f"CC cannot get from '{listname}' — it is not a list.")
            idx = int(evaluate(expr, memory))
            if idx < 0 or idx >= len(memory[listname]):
                raise Exception(f"CC refuses — index {idx} is out of bounds.")
            memory[varname] = memory[listname][idx]

        elif instruction[0] == "SIZE":
            listname, varname = instruction[1], instruction[2]
            if listname not in memory or not isinstance(memory[listname], list):
                raise Exception(f"CC cannot size '{listname}' — it is not a list.")
            memory[varname] = len(memory[listname])

        elif instruction[0] == "LENGTH":
            name, result = instruction[1], instruction[2]
            memory[result] = len(str(memory.get(name, "")))

        elif instruction[0] == "JOIN":
            a, b, result = instruction[1], instruction[2], instruction[3]
            va = str(memory[a]) if a in memory else a
            vb = str(memory[b]) if b in memory else b
            memory[result] = va + vb

        elif instruction[0] == "SLICE":
            name, start_expr, end_expr, result = instruction[1], instruction[2], instruction[3], instruction[4]
            val   = str(memory[name])
            start = int(evaluate(start_expr, memory))
            end   = int(evaluate(end_expr,   memory))
            memory[result] = val[start:end]

        elif instruction[0] == "WRITE":
            filename = str(evaluate(instruction[1], memory))
            content  = str(evaluate(instruction[2], memory))
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)

        elif instruction[0] == "READ":
            filename = str(evaluate(instruction[1], memory))
            varname  = instruction[2]
            if not os.path.exists(filename):
                raise Exception(f"CC cannot read '{filename}' — the file does not exist.")
            with open(filename, 'r', encoding='utf-8') as f:
                memory[varname] = f.read()

        elif instruction[0] == "INVOKE":
            module = instruction[1]
            if module not in ["RANDOM", "TIME", "MATH", "HTTP", "JSON"]:
                raise Exception(f"CC does not know the module '{module}'.")
            invoked.add(module)

        elif instruction[0] == "RANDOM":
            if "RANDOM" not in invoked:
                raise Exception("CC refuses — you must INVOKE RANDOM before using it.")
            min_val = int(evaluate(instruction[1], memory))
            max_val = int(evaluate(instruction[2], memory))
            memory[instruction[3]] = random.randint(min_val, max_val)

        elif instruction[0] == "TIME_GET":
            if "TIME" not in invoked:
                raise Exception("CC refuses — you must INVOKE TIME before using it.")
            memory[instruction[1]] = time.time()

        elif instruction[0] == "MATH":
            if "MATH" not in invoked:
                raise Exception("CC refuses — you must INVOKE MATH before using it.")
            func = instruction[1]
            val  = evaluate(instruction[2], memory)
            funcs = {
                "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
                "abs": abs, "round": round, "sin": math.sin,
                "cos": math.cos, "tan": math.tan, "log": math.log,
            }
            if func not in funcs:
                raise Exception(f"CC does not know the MATH function '{func}'.")
            memory[instruction[3]] = funcs[func](val)

        elif instruction[0] == "ORD":
            src_token, result = instruction[1], instruction[2]
            kind, val = src_token
            if kind == "STRING":
                ch = val
            elif kind == "NAME":
                ch = str(memory.get(val, ""))
            else:
                ch = str(val)
            if len(ch) == 0:
                raise Exception("CC cannot ORD an empty string.")
            memory[result] = ord(ch[0])

        elif instruction[0] == "CHR":
            expr, result = instruction[1], instruction[2]
            code = int(evaluate(expr, memory))
            memory[result] = chr(code)

        elif instruction[0] == "MOD":
            a = int(evaluate(instruction[1], memory))
            b = int(evaluate(instruction[2], memory))
            if b == 0:
                raise Exception("CC refuses to mod by zero.")
            memory[instruction[3]] = a % b

        # --- HTTP ---

        elif instruction[0] == "FETCH":
            if "HTTP" not in invoked:
                raise Exception("CC refuses — you must INVOKE HTTP before using it.")
            _, url_expr, path_expr, headers_var, resp_var, on_fail = instruction
            url  = str(evaluate(url_expr,  memory))
            path = str(evaluate(path_expr, memory)) if path_expr else ""
            make_request("GET", url, path, headers_var, None, on_fail, memory)

        elif instruction[0] == "HTTP_METHOD":
            if "HTTP" not in invoked:
                raise Exception("CC refuses — you must INVOKE HTTP before using it.")
            _, method, url_expr, path_expr, body_expr, headers_var, resp_var, on_fail = instruction
            url  = str(evaluate(url_expr,  memory))
            path = str(evaluate(path_expr, memory)) if path_expr else ""
            body = str(evaluate(body_expr, memory)) if body_expr else None
            make_request(method, url, path, headers_var, body, on_fail, memory)

        elif instruction[0] == "PARSE":
            if "JSON" not in invoked:
                raise Exception("CC refuses — you must INVOKE JSON before using it.")
            src_expr, result = instruction[1], instruction[2]
            raw = str(evaluate(src_expr, memory))
            try:
                memory[result] = json.loads(raw)
            except json.JSONDecodeError as e:
                raise Exception(f"CC cannot parse JSON — {e}")

        elif instruction[0] == "PLUCK":
            if "JSON" not in invoked:
                raise Exception("CC refuses — you must INVOKE JSON before using it.")
            data_var, key_expr, result = instruction[1], instruction[2], instruction[3]
            data = memory.get(data_var)
            key  = str(evaluate(key_expr, memory))
            if isinstance(data, dict):
                if key not in data:
                    raise Exception(f"CC cannot find key '{key}' in the data.")
                val = data[key]
                memory[result] = json.dumps(val) if isinstance(val, (dict, list)) else val
            else:
                raise Exception(f"CC cannot PLUCK from '{data_var}' — it is not parsed JSON.")

        elif instruction[0] == "PRETTY":
            src_expr = instruction[1]
            raw = evaluate(src_expr, memory)
            if isinstance(raw, (dict, list)):
                print(json.dumps(raw, indent=2))
            else:
                try:
                    parsed = json.loads(str(raw))
                    print(json.dumps(parsed, indent=2))
                except Exception:
                    print(str(raw))

        elif instruction[0] == "HEADER":
            key_expr, val_expr, result = instruction[1], instruction[2], instruction[3]
            k = str(evaluate(key_expr, memory))
            v = str(evaluate(val_expr, memory))
            memory[result] = f"{k}: {v}"

        elif instruction[0] == "BEARER":
            tok_expr, result = instruction[1], instruction[2]
            tok = str(evaluate(tok_expr, memory))
            memory[result] = f"Authorization: Bearer {tok}"

        elif instruction[0] == "BASIC":
            import base64
            user_expr, pass_expr, result = instruction[1], instruction[2], instruction[3]
            user = str(evaluate(user_expr, memory))
            pwd  = str(evaluate(pass_expr, memory))
            encoded = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            memory[result] = f"Authorization: Basic {encoded}"

        elif instruction[0] == "SHOW":
            skip = {"__constants__", "__invoked__"}
            print("\n[CC MEMORY]")
            for k, v in memory.items():
                if k in skip:
                    continue
                if isinstance(v, tuple) and len(v) > 0 and v[0] == "__contract__":
                    print(f"  {k} = <contract>")
                elif isinstance(v, list):
                    print(f"  {k} = {v}")
                elif isinstance(v, dict):
                    print(f"  {k} = {{...}} ({len(v)} keys)")
                else:
                    print(f"  {k} = {repr(v)}")
            print()

        elif instruction[0] == "ENV":
            key_expr, result = instruction[1], instruction[2]
            key = str(evaluate(key_expr, memory))
            val = os.environ.get(key)
            if val is None:
                raise Exception(f"CC cannot find environment variable '{key}'.")
            memory[result] = val

        elif instruction[0] == "DOTENV":
            path_expr = instruction[1]
            filepath = str(evaluate(path_expr, memory))
            load_dotenv(filepath, memory)


# --- REPL ---

HISTORY_FILE = os.path.expanduser("~/.cc_history")

def setup_history():
    if not HAS_READLINE:
        return
    try:
        if os.path.exists(HISTORY_FILE):
            readline.read_history_file(HISTORY_FILE)
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, HISTORY_FILE)
    except Exception:
        pass


def run_repl():
    setup_history()
    memory = {}

    print("CC — HTTP Scripting Language")
    print("type CC commands, SHOW to inspect memory, exit to quit")
    if HAS_READLINE:
        print(f"history: {HISTORY_FILE}")
    else:
        print("tip: pip install pyreadline3 for command history on Windows")
    print()

    while True:
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCC out.")
            break

        if not line:
            continue

        if line.lower() in ("exit", "quit", "q"):
            print("CC out.")
            break

        try:
            tokens = lex(line)
            instructions = parse(tokens)
            interpret(instructions, memory)
        except StopSignal:
            pass
        except Exception as e:
            print(f"[CC] {e}")


# --- MAIN ---

if len(sys.argv) < 2:
    run_repl()
else:
    try:
        source = open(sys.argv[1], encoding='utf-8').read()
        tokens = lex(source)
        instructions = parse(tokens)
        interpret(instructions)
    except StopSignal:
        pass
    except Exception as e:
        print(f"\n[CC] {e}")