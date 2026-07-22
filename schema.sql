-- ============================================================
-- ESQUEMA DE BASE DE DATOS (PostgreSQL) - Sistema de Loterías
-- ============================================================
-- Misma estructura que ya conoces, adaptada de SQLite a
-- PostgreSQL: los IDs ahora usan SERIAL en vez de AUTOINCREMENT.
-- ============================================================

CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    nombre          TEXT NOT NULL,
    usuario         TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    rol             TEXT NOT NULL CHECK (rol IN ('master', 'banquero', 'agencia', 'caja')),
    activo          INTEGER NOT NULL DEFAULT 1,
    creado_en       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE banqueros (
    id                      SERIAL PRIMARY KEY,
    usuario_id              INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    comision_sistema_pct    REAL NOT NULL,
    afiliacion_pagada       REAL DEFAULT 0,
    activo                  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE agencias (
    id                          SERIAL PRIMARY KEY,
    banquero_id                 INTEGER NOT NULL REFERENCES banqueros(id),
    usuario_admin_id            INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    nombre                      TEXT NOT NULL,
    comision_pct                REAL NOT NULL,
    tiempo_anulacion_min        INTEGER NOT NULL DEFAULT 5,
    servicio_resultados_activo  INTEGER NOT NULL DEFAULT 0,
    quien_carga_resultados      TEXT NOT NULL DEFAULT 'agencia' CHECK (quien_carga_resultados IN ('agencia', 'proveedor')),
    comision_resultados_pct     REAL DEFAULT 0,
    activa                      INTEGER NOT NULL DEFAULT 1,
    creado_en                   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE cajas (
    id            SERIAL PRIMARY KEY,
    agencia_id    INTEGER NOT NULL REFERENCES agencias(id),
    usuario_id    INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    nombre_caja   TEXT NOT NULL,
    activo        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE loterias (
    id                  SERIAL PRIMARY KEY,
    nombre              TEXT NOT NULL UNIQUE,
    cantidad_numeros    INTEGER NOT NULL,
    pago_normal         REAL NOT NULL,
    pago_aproximacion   REAL DEFAULT 0,
    numero_comodin      TEXT,
    pago_comodin        REAL,
    creado_en           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE sorteos (
    id                  SERIAL PRIMARY KEY,
    loteria_id          INTEGER NOT NULL REFERENCES loterias(id),
    hora                TEXT NOT NULL,
    minutos_cierre_antes INTEGER NOT NULL DEFAULT 5,
    activo              INTEGER NOT NULL DEFAULT 1,
    dias_semana         TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7'
);

CREATE TABLE tickets (
    id              SERIAL PRIMARY KEY,
    agencia_id      INTEGER NOT NULL REFERENCES agencias(id),
    caja_id         INTEGER NOT NULL REFERENCES cajas(id),
    numero_ticket   TEXT NOT NULL UNIQUE,
    serial          TEXT NOT NULL UNIQUE,
    moneda          TEXT NOT NULL CHECK (moneda IN ('BOLIVAR', 'DOLARES')),
    total            REAL NOT NULL,
    estado           TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'anulado', 'pagado')),
    vendido_en       TIMESTAMP NOT NULL DEFAULT NOW(),
    vence_en         TIMESTAMP NOT NULL
);

CREATE TABLE jugadas (
    id              SERIAL PRIMARY KEY,
    ticket_id       INTEGER NOT NULL REFERENCES tickets(id),
    sorteo_id       INTEGER NOT NULL REFERENCES sorteos(id),
    tipo_jugada     TEXT NOT NULL CHECK (tipo_jugada IN ('animalito', 'terminal', 'triple', 'tripleta')),
    numero_jugado   TEXT NOT NULL,
    monto           REAL NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'ganador', 'perdedor')),
    premio          REAL DEFAULT 0,
    premio_pagado   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE resultados (
    id              SERIAL PRIMARY KEY,
    sorteo_id       INTEGER NOT NULL REFERENCES sorteos(id),
    fecha           TEXT NOT NULL,
    numero_ganador  TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'procesado')),
    registrado_por  INTEGER REFERENCES usuarios(id),
    procesado_en    TIMESTAMP
);

CREATE TABLE bloqueos_limites (
    id              SERIAL PRIMARY KEY,
    nivel           TEXT NOT NULL CHECK (nivel IN ('agencia', 'banquero')),
    nivel_id        INTEGER NOT NULL,
    loteria_id      INTEGER NOT NULL REFERENCES loterias(id),
    sorteo_id       INTEGER REFERENCES sorteos(id),
    numero          TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('bloqueado', 'limite')),
    monto_limite    REAL
);

CREATE INDEX idx_tickets_agencia ON tickets(agencia_id);
CREATE INDEX idx_tickets_caja ON tickets(caja_id);
CREATE INDEX idx_jugadas_ticket ON jugadas(ticket_id);
CREATE INDEX idx_jugadas_sorteo ON jugadas(sorteo_id);
CREATE INDEX idx_resultados_sorteo_fecha ON resultados(sorteo_id, fecha);
CREATE INDEX idx_bloqueos_nivel ON bloqueos_limites(nivel, nivel_id);
