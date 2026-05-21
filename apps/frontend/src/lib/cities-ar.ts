export interface City {
  name: string
  province: string
  lat: number
  lon: number
}

export const AR_CITIES: City[] = [
  { name: 'Buenos Aires', province: 'CABA', lat: -34.6037, lon: -58.3816 },
  { name: 'Córdoba', province: 'Córdoba', lat: -31.4135, lon: -64.181 },
  { name: 'Rosario', province: 'Santa Fe', lat: -32.9587, lon: -60.6931 },
  { name: 'Mendoza', province: 'Mendoza', lat: -32.8895, lon: -68.8458 },
  { name: 'Tucumán', province: 'Tucumán', lat: -26.8083, lon: -65.2176 },
  { name: 'La Plata', province: 'Buenos Aires', lat: -34.9205, lon: -57.9536 },
  { name: 'Mar del Plata', province: 'Buenos Aires', lat: -38.0, lon: -57.5667 },
  { name: 'Salta', province: 'Salta', lat: -24.7859, lon: -65.4117 },
  { name: 'Santa Fe', province: 'Santa Fe', lat: -31.6333, lon: -60.7 },
  { name: 'San Juan', province: 'San Juan', lat: -31.5375, lon: -68.5364 },
  { name: 'Resistencia', province: 'Chaco', lat: -27.46, lon: -58.9867 },
  { name: 'Neuquén', province: 'Neuquén', lat: -38.9516, lon: -68.0591 },
  { name: 'Santiago del Estero', province: 'Santiago del Estero', lat: -27.7951, lon: -64.2615 },
  { name: 'Corrientes', province: 'Corrientes', lat: -27.4692, lon: -58.8306 },
  { name: 'Posadas', province: 'Misiones', lat: -27.3671, lon: -55.8964 },
  { name: 'San Salvador de Jujuy', province: 'Jujuy', lat: -24.1858, lon: -65.2995 },
  { name: 'Bahía Blanca', province: 'Buenos Aires', lat: -38.7196, lon: -62.2724 },
  { name: 'Paraná', province: 'Entre Ríos', lat: -31.7333, lon: -60.5333 },
  { name: 'Formosa', province: 'Formosa', lat: -26.1775, lon: -58.1781 },
  { name: 'San Luis', province: 'San Luis', lat: -33.295, lon: -66.3356 },
  { name: 'La Rioja', province: 'La Rioja', lat: -29.4, lon: -66.85 },
  { name: 'Catamarca', province: 'Catamarca', lat: -28.4696, lon: -65.7852 },
  { name: 'Rawson', province: 'Chubut', lat: -43.3002, lon: -65.1023 },
  { name: 'Río Gallegos', province: 'Santa Cruz', lat: -51.6226, lon: -69.2181 },
  { name: 'Ushuaia', province: 'Tierra del Fuego', lat: -54.8, lon: -68.3 },
  { name: 'Viedma', province: 'Río Negro', lat: -40.8135, lon: -62.9967 },
  { name: 'Santa Rosa', province: 'La Pampa', lat: -36.6167, lon: -64.2833 },
  { name: 'Bariloche', province: 'Río Negro', lat: -41.1335, lon: -71.3103 },
  { name: 'Comodoro Rivadavia', province: 'Chubut', lat: -45.8645, lon: -67.4853 },
  { name: 'Tandil', province: 'Buenos Aires', lat: -37.3217, lon: -59.1332 },
  { name: 'Junín', province: 'Buenos Aires', lat: -34.5921, lon: -60.9558 },
  { name: 'San Rafael', province: 'Mendoza', lat: -34.6177, lon: -68.3301 },
  { name: 'Villa Mercedes', province: 'San Luis', lat: -33.675, lon: -65.4597 },
  { name: 'Concordia', province: 'Entre Ríos', lat: -31.3927, lon: -58.0199 },
  { name: 'Olavarría', province: 'Buenos Aires', lat: -36.8924, lon: -60.3228 },
  { name: 'Río Cuarto', province: 'Córdoba', lat: -33.1232, lon: -64.3493 },
  { name: 'Moreno', province: 'Buenos Aires', lat: -34.4157, lon: -58.5634 },
  { name: 'Zárate', province: 'Buenos Aires', lat: -34.0982, lon: -59.0278 },
  { name: 'Pergamino', province: 'Buenos Aires', lat: -33.8899, lon: -60.5705 },
  { name: 'San Nicolás', province: 'Buenos Aires', lat: -33.3333, lon: -60.2167 },
  { name: 'Lomas de Zamora', province: 'Buenos Aires', lat: -34.7611, lon: -58.4032 },
  { name: 'Quilmes', province: 'Buenos Aires', lat: -34.7228, lon: -58.2592 },
  { name: 'Lanús', province: 'Buenos Aires', lat: -34.7007, lon: -58.3908 },
  { name: 'Morón', province: 'Buenos Aires', lat: -34.6534, lon: -58.6198 },
  { name: 'San Miguel', province: 'Buenos Aires', lat: -34.5422, lon: -58.7079 },
  { name: 'Malargüe', province: 'Mendoza', lat: -35.4765, lon: -69.5839 },
  { name: 'Caleta Olivia', province: 'Santa Cruz', lat: -46.4333, lon: -67.5167 },
  { name: 'Puerto Madryn', province: 'Chubut', lat: -42.7682, lon: -65.0366 },
  { name: 'Esquel', province: 'Chubut', lat: -42.9144, lon: -71.3187 },
  { name: 'El Calafate', province: 'Santa Cruz', lat: -50.3375, lon: -72.2742 },
]

function normalize(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
}

export function searchCities(query: string): City[] {
  const q = normalize(query.trim())
  if (!q) return []
  return AR_CITIES.filter(
    (c) => normalize(c.name).includes(q) || normalize(c.province).includes(q)
  ).slice(0, 8)
}
