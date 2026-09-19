import type { Config } from 'svgo'

type PluginConfig = NonNullable<Config['plugins']>[number]
type CustomPlugin = Extract<PluginConfig, { fn: unknown }>
type XastRoot = Parameters<CustomPlugin['fn']>[0]
type XastChild = XastRoot['children'][number]
type XastElement = Extract<XastChild, { type: 'element' }>

/** Separador de `prefixIds` (su valor por defecto): "rain_svg" + "__" + "d". */
const DELIM = '__'

/** Referencia de sincronización de SMIL al inicio de un valor `begin`/`end`: "d.end", "d.begin", "d.start". */
const SYNCBASE = /^(\s*)([A-Za-z_][\w-]*)\.(begin|end|start)(?=$|[+\-\s])/

/** id sin prefijo → id con prefijo, para todos los ids del documento que llevan el prefijo. */
function collectPrefixedIds(node: XastRoot | XastElement, out: Map<string, string>): void {
  for (const child of node.children) {
    if (child.type !== 'element') continue
    const id = child.attributes.id
    if (id) {
      const at = id.lastIndexOf(DELIM)
      if (at !== -1) out.set(id.slice(at + DELIM.length), id)
    }
    collectPrefixedIds(child, out)
  }
}

/**
 * SVGO 3.3.3: `prefixIds` solo reescribe las referencias `begin`/`end` que TERMINAN en ".end" o
 * ".start". Los Meteocons encadenan sus bucles con un desfase ("0s; d.end+.33s"), así que esas
 * referencias quedaban apuntando a un id sin prefijo que ya no existe: el bucle SMIL nunca
 * reinicia y las gotas de lluvia y nieve aparecen una vez y desaparecen.
 *
 * Corre DESPUÉS de `prefixIds` y completa el prefijo donde quedó sin reescribir. Idempotente:
 * una referencia que ya lleva prefijo no coincide con ningún id sin prefijo.
 */
export const smilPrefixedRefs: CustomPlugin = {
  name: 'smil-prefixed-refs',
  fn: (root) => {
    const prefixed = new Map<string, string>()
    collectPrefixedIds(root, prefixed)

    return {
      element: {
        enter: (node) => {
          for (const attribute of ['begin', 'end'] as const) {
            const value = node.attributes[attribute]
            if (!value) continue
            node.attributes[attribute] = value
              .split(';')
              .map((part) =>
                part.replace(SYNCBASE, (match, space: string, id: string, event: string) => {
                  const full = prefixed.get(id)
                  return full ? `${space}${full}.${event}` : match
                }),
              )
              .join(';')
          }
        },
      },
    }
  },
}

/** Pipeline SVGO de los Meteocons (SVGR): minificar, prefijar ids por archivo y arreglar los bucles SMIL. */
export const meteoconsSvgoPlugins: PluginConfig[] = [
  { name: 'preset-default' },
  { name: 'prefixIds' },
  smilPrefixedRefs,
]
