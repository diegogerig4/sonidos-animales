# Cambia las categorias de la app por grupos biologicos. Se puede ejecutar varias veces sin problema.
p = 'tools/template.html'
s = open(p, encoding='utf-8').read()
a = s.index('const CATS = [')
b = s.index('\n', s.index('const CAT_ICON')) + 1
new = '''const CATS = [
  { k: "todos", name: "Todos", c: "var(--todos)" },
  { k: "mamiferos", name: "Mamíferos", c: "var(--granja)" },
  { k: "aves", name: "Aves", c: "var(--pajaros)" },
  { k: "reptiles", name: "Reptiles", c: "var(--selva)" },
  { k: "anfibios", name: "Anfibios", c: "var(--mar)" },
  { k: "insectos", name: "Insectos", c: "var(--casa)" },
  { k: "mas", name: "Más", c: "var(--mas)" }
];
const CAT_ICON = { todos: "leon", mamiferos: "elefante", aves: "petirrojo", reptiles: "caiman", anfibios: "rana", insectos: "abeja" };
'''
s = s[:a] + new + s[b:]
s = s.replace('const cats = CATS.filter(c => c.k !== "mas" || EXTRA.length);', 'const cats = CATS.filter(c => c.k === "todos" || listFor(c.k).length);')
open(p, 'w', encoding='utf-8').write(s)
print('categorias ok')
