TYPE = {"beam": "Segment"}  # vocab -> concrete node type
PROP = {"length": "length", "thickness": "thickness", "material":"material"}

def t(name: str) -> str: return TYPE.get(name, name)
def p(name: str) -> str: return PROP.get(name, name)

