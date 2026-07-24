export const validPrevifocFixture = {
  c: "1",
  v: 5,
  t: 3,
  z1: [
    { id: 59, nact: 9, npre: 4 },
    { id: 53, nact: 1, npre: 1 },
    { id: 57, nact: 5, npre: 5 },
    { id: 55, nact: 3, npre: 3 },
    { id: 58, nact: 7, npre: 7 },
    { id: 54, nact: 2, npre: 2 },
    { id: 56, nact: 4, npre: 4 },
  ],
  time: "2026-07-18 00:01:41.0",
  desEs: "<p>fixture deliberately not consumed</p>",
  desVa: "<p>fixture deliberately not consumed</p>",
  desPreEs: "<p>fixture deliberately not consumed</p>",
  desPreVa: "<p>fixture deliberately not consumed</p>",
  isFileAH: false,
};

export const invalidDuplicateZoneFixture = {
  ...validPrevifocFixture,
  z1: [
    ...validPrevifocFixture.z1.slice(0, 6),
    { id: 53, nact: 4, npre: 4 },
  ],
};

const previfocSituations = Array.from({ length: 9 }, (_, index) => {
  const situationId = index + 1;
  return {
    ID_SITUACION: situationId,
    DESCRIPCION_ES: `Nivel ${Math.ceil(situationId / 3)} fixture`,
    DESCRIPCION_VA: `Nivell ${Math.ceil(situationId / 3)} fixture`,
    COLOR: null,
    FECHA_ALTA: "2025-06-26T09:00:00.000Z",
    FIRMA_USUARIO: "fixture",
    ID_AVISO: 3,
    ACTIVO: "S",
  };
});

export const validSituacionFixture = {
  SITUACION: [
    {
      ID_SITUACION: 10,
      DESCRIPCION_ES: "VERDE",
      DESCRIPCION_VA: "VERD",
      COLOR: null,
      FECHA_ALTA: "2025-06-26T09:13:30.000Z",
      FIRMA_USUARIO: "fixture",
      ID_AVISO: 1,
      ACTIVO: "S",
    },
    ...previfocSituations,
    {
      ID_SITUACION: 14,
      DESCRIPCION_ES: "SITUACIÓN 0",
      DESCRIPCION_VA: "SITUACIÓ 0",
      COLOR: null,
      FECHA_ALTA: "2025-06-30T06:35:42.000Z",
      FIRMA_USUARIO: "fixture",
      ID_AVISO: 2,
      ACTIVO: "S",
    },
  ],
};

export const invalidWrongAdvisoryFixture = {
  SITUACION: validSituacionFixture.SITUACION.map((situation) =>
    situation.ID_SITUACION === 5
      ? { ...situation, ID_AVISO: 1 }
      : { ...situation },
  ),
};

export function cloneFixture<T>(fixture: T): T {
  return structuredClone(fixture);
}
