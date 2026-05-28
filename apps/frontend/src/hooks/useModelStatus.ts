import { useContext, type Dispatch } from 'react'
import {
  ModelStatusContext,
  ModelStatusDispatchContext,
  type ModelStatusState,
  type ModelStatusAction,
} from '@/contexts/ModelStatusContext'

export function useModelStatus(): { status: ModelStatusState } {
  const ctx = useContext(ModelStatusContext)
  if (ctx === null) {
    throw new Error('useModelStatus must be used inside ModelStatusProvider')
  }
  return { status: ctx }
}

export function useModelStatusDispatch(): Dispatch<ModelStatusAction> {
  const ctx = useContext(ModelStatusDispatchContext)
  if (ctx === null) {
    throw new Error('useModelStatusDispatch must be used inside ModelStatusProvider')
  }
  return ctx
}
