-- ============================================================
-- ESQUEMA DE BASE DE DATOS - Sistema de Ventas de Loterías
-- ============================================================
-- Este archivo crea todas las "carpetas" (tablas) donde el
-- sistema va a guardar su información. Está organizado en el
-- mismo orden que hablamos en el chat: usuarios y jerarquía,
-- loterías y sorteos, ventas, resultados, y reglas de negocio.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 1. USUARIOS Y JERARQUÍA
-- ------------------------------------------------------------
-- Toda persona que entra al sistema (Master, Banquero, Admin de
-- Agencia, Caja) es un "usuario". El campo "rol" dice qué tipo
-- de panel le corresponde ver al iniciar sesión.

CREATE TABLE usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,              -- nombre completo de la persona
    usuario         TEXT NOT NULL UNIQUE,        -- con lo que inicia sesión
    password_hash   TEXT NOT NULL,               -- la contraseña, cifrada (nunca en texto plano)
    rol             TEXT NOT NULL CHECK (rol IN ('master', 'banquero', 'agencia', 'caja')),
    activo          INTEGER NOT NULL DEFAULT 1,  -- 1 = puede entrar, 0 = bloqueado
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Un Banquero es un usuario con rol 'banquero', más sus datos de negocio.
CREATE TABLE banqueros (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id              INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    comision_sistema_pct    REAL NOT NULL,       -- % que le cobra el Master por usar el sistema
    afiliacion_pagada       REAL DEFAULT 0,      -- pago único registrado al crearlo
    activo                  INTEGER NOT NULL DEFAULT 1
);

-- Una Agencia pertenece a un Banquero, y tiene su propio usuario administrador.
CREATE TABLE agencias (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    banquero_id                 INTEGER NOT NULL REFERENCES banqueros(id),
    usuario_admin_id            INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    nombre                      TEXT NOT NULL,
    comision_pct                REAL NOT NULL,   -- % que le paga el banquero a esta agencia
    tiempo_anulacion_min        INTEGER NOT NULL DEFAULT 5,  -- configurable: 3, 5 o 10
    servicio_resultados_activo  INTEGER NOT NULL DEFAULT 0,  -- lo activa el Master
    quien_carga_resultados      TEXT NOT NULL DEFAULT 'agencia' CHECK (quien_carga_resultados IN ('agencia', 'proveedor')),
    comision_resultados_pct     REAL DEFAULT 0,  -- 0% a 2.50%, lo pone el Master
    activa                      INTEGER NOT NULL DEFAULT 1,
    creado_en                   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Una Caja (taquilla) pertenece a una Agencia. Gana sueldo, no comisión.
CREATE TABLE cajas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agencia_id    INTEGER NOT NULL REFERENCES agencias(id),
    usuario_id    INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    nombre_caja   TEXT NOT NULL,      -- ej. "Caja 1", "Caja 2"
    activo        INTEGER NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------
-- 2. LOTERÍAS Y SORTEOS
-- ------------------------------------------------------------
-- El catálogo de loterías lo administra el Master. Cada lotería
-- define cuánto paga y si tiene número comodín.

CREATE TABLE loterias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL UNIQUE,
    cantidad_numeros    INTEGER NOT NULL,        -- ej. 38, 77, 102
    pago_normal         REAL NOT NULL,           -- veces lo apostado, ej. 30
    pago_aproximacion   REAL DEFAULT 0,          -- 0 = no aplica
    numero_comodin      TEXT,                    -- ej. '75', NULL si no tiene
    pago_comodin        REAL,                    -- veces lo apostado para el comodín
    creado_en           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Los horarios en que sortea cada lotería (ej. La Granjita: cada hora 8am-7pm).
CREATE TABLE sorteos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    loteria_id          INTEGER NOT NULL REFERENCES loterias(id),
    hora                TEXT NOT NULL,           -- ej. '14:00'
    minutos_cierre_antes INTEGER NOT NULL DEFAULT 5,  -- cierra la venta X min antes
    activo              INTEGER NOT NULL DEFAULT 1,   -- se puede apagar (ej. feriado)
    dias_semana         TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7'  -- 1=lunes ... 7=domingo
);

-- ------------------------------------------------------------
-- 3. VENTAS: TICKETS Y JUGADAS
-- ------------------------------------------------------------

CREATE TABLE tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agencia_id      INTEGER NOT NULL REFERENCES agencias(id),
    caja_id         INTEGER NOT NULL REFERENCES cajas(id),   -- quién lo vendió
    numero_ticket   TEXT NOT NULL UNIQUE,     -- lo que ve el vendedor (N/T)
    serial          TEXT NOT NULL UNIQUE,     -- solo va impreso, sirve para pagar
    moneda          TEXT NOT NULL CHECK (moneda IN ('BOLIVAR', 'DOLARES')),
    total            REAL NOT NULL,
    estado           TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'anulado', 'pagado')),
    vendido_en       TEXT NOT NULL DEFAULT (datetime('now')),  -- hora del SERVIDOR
    vence_en         TEXT NOT NULL             -- vendido_en + 3 días (configurable)
);

-- Cada jugada dentro de un ticket (un ticket puede tener varias).
CREATE TABLE jugadas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       INTEGER NOT NULL REFERENCES tickets(id),
    sorteo_id       INTEGER NOT NULL REFERENCES sorteos(id),
    tipo_jugada     TEXT NOT NULL CHECK (tipo_jugada IN ('animalito', 'terminal', 'triple', 'tripleta')),
    numero_jugado   TEXT NOT NULL,        -- ej. '28' o para tripleta '09-18-20'
    monto           REAL NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'ganador', 'perdedor')),
    premio          REAL DEFAULT 0,
    premio_pagado   INTEGER NOT NULL DEFAULT 0   -- 0 = por pagar, 1 = ya pagado
);

-- ------------------------------------------------------------
-- 4. RESULTADOS
-- ------------------------------------------------------------
-- Un resultado es único por lotería+sorteo (no depende de agencia).

CREATE TABLE resultados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sorteo_id       INTEGER NOT NULL REFERENCES sorteos(id),
    fecha           TEXT NOT NULL,          -- día del sorteo
    numero_ganador  TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'procesado')),
    registrado_por  INTEGER REFERENCES usuarios(id),
    procesado_en    TEXT
);

-- ------------------------------------------------------------
-- 5. BLOQUEOS Y LÍMITES
-- ------------------------------------------------------------
-- Quien lo puso puede ser una agencia o un banquero (aplica a
-- todas sus agencias). "sorteo_id" es NULL si aplica a toda la
-- lotería en vez de a una hora específica.

CREATE TABLE bloqueos_limites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nivel           TEXT NOT NULL CHECK (nivel IN ('agencia', 'banquero')),
    nivel_id        INTEGER NOT NULL,       -- id de la agencia o del banquero
    loteria_id      INTEGER NOT NULL REFERENCES loterias(id),
    sorteo_id       INTEGER REFERENCES sorteos(id),  -- NULL = toda la lotería
    numero          TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('bloqueado', 'limite')),
    monto_limite    REAL                     -- solo si tipo = 'limite'
);

-- ------------------------------------------------------------
-- Índices para que las consultas frecuentes sean rápidas
-- ------------------------------------------------------------
CREATE INDEX idx_tickets_agencia ON tickets(agencia_id);
CREATE INDEX idx_tickets_caja ON tickets(caja_id);
CREATE INDEX idx_jugadas_ticket ON jugadas(ticket_id);
CREATE INDEX idx_jugadas_sorteo ON jugadas(sorteo_id);
CREATE INDEX idx_resultados_sorteo_fecha ON resultados(sorteo_id, fecha);
CREATE INDEX idx_bloqueos_nivel ON bloqueos_limites(nivel, nivel_id);
