# CC Language

An HTTP scripting language. Hit APIs, handle responses, chain requests — with logic built in.

# Install

Download `cc.exe` from [Releases](https://github.com/tetoismommy-lgtm/cc-lang/releases/latest).

Add it to your PATH, then:
cc myprogram.cc

## Quick Example
INVOKE HTTP
INVOKE JSON
FETCH "https://api.github.com" "/zen" INTO response OR FAIL
SPEAK response_body

## Documentation

Open `cc-docs.html` in your browser for the full reference.

## Built by Demir Magalov :D
