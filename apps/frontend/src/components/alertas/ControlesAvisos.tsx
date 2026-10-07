import { useEffect, useId, useRef } from 'react'
import type { AvisosPush } from '@/hooks/useAvisosPush'
import { zonaPorSlug } from '@/lib/alertas/zonaSugerida'
import { AccionesAvisos } from './AccionesAvisos'
import { ConsentimientoAvisos } from './ConsentimientoAvisos'
import { RegionEstado } from './RegionEstado'
import { SelectorZona } from './SelectorZona'

interface ControlesAvisosProps {
  avisos: AvisosPush
  /** Nombre de la ciudad más cercana a la ubicación, si hay. */
  nombreSugerida: string | null
}

/**
 * Lo que se ve cuando el navegador puede recibir avisos: ciudad, consentimiento y botones mientras no hay
 * avisos; los botones de probar y desactivar con ellos. La región de estado va siempre al final y siempre
 * montada, para que el lector de pantalla anuncie lo que cambia.
 */
export function ControlesAvisos({ avisos, nombreSugerida }: ControlesAvisosProps) {
  const idEstado = useId()
  const regionRef = useRef<HTMLDivElement>(null)
  const { estado } = avisos
  const activo = estado.tipo === 'activo'
  const eraActivo = useRef(activo)
  const nombreActiva = estado.tipo === 'activo' ? (zonaPorSlug(estado.zona)?.nombre ?? null) : null

  // Al activar o desactivar, el botón que tenía el foco se reemplaza por otros: si el foco quedó sin lugar
  // (en el <body>), pasa a la región de estado, que además lee el resultado. Si la persona estaba en otro
  // control no se le quita. Esto no pide ni cambia nada: solo mueve el foco.
  useEffect(() => {
    if (eraActivo.current !== activo) {
      const foco = document.activeElement
      if (foco === null || foco === document.body) regionRef.current?.focus()
    }
    eraActivo.current = activo
  }, [activo])

  return (
    <div className="space-y-5">
      {estado.tipo !== 'activo' && (
        <>
          <SelectorZona valor={avisos.zonaElegida} onCambio={avisos.setZona} nombreSugerida={nombreSugerida} />
          <ConsentimientoAvisos marcado={avisos.consentimiento} onCambio={avisos.setConsentimiento} />
        </>
      )}
      <AccionesAvisos
        estado={estado}
        puedeActivar={avisos.puedeActivar}
        ocupado={avisos.ocupado}
        prueba={avisos.prueba}
        esperaProbar={avisos.esperaProbar}
        idEstado={idEstado}
        onActivar={() => void avisos.activar()}
        onProbar={() => void avisos.probar()}
        onDesactivar={() => void avisos.desactivar()}
      />
      <RegionEstado
        id={idEstado}
        regionRef={regionRef}
        estado={estado}
        nombreZona={nombreActiva}
        prueba={avisos.prueba}
      />
    </div>
  )
}
