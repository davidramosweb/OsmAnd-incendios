# GEO-002 — Informe del crosswalk municipal

Este informe corresponde al crosswalk reproducible de 542 municipios. No modifica ni procesa geometrías.

## Procedencia fijada

| Fuente | Snapshot de GEO-001 | SHA-256 crudo | Huella lógica | Licencia |
|---|---|---|---|---|
| `municipios_112cv` | `snapshots/municipios_112cv/5d80c0b9a40c29beca831c964ef11b254d0f5a0c5c765acd77dc355ddd54370d.json` | `5d80c0b9a40c29beca831c964ef11b254d0f5a0c5c765acd77dc355ddd54370d` | `a1a2c18581507e2c19167a5cd9633110abddd8484bf93296be23ee88f54c6d06` | not_found |
| `icv_municipios` | `snapshots/icv_municipios/acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276.gpkg` | `acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276` | `f384ce5ec703a3f2ed4173337f8d80aa24e502cf015f2a3124f30a29506130df` | declared |

Las rutas anteriores se resolvieron desde `data/sources/manifest.json`; no se consultó ninguna URL viva. `Fuera C.V.` se comprobó contra el registro fijado y se excluyó explícitamente.

La licencia ICV sigue declarada como `CC BY 4.0 Generalitat`. La licencia específica de 112CV continúa en estado `not_found`: esta ausencia no bloquea el trabajo local, pero sí debe resolverse antes de reutilización pública.

## Resultado

- Filas: **542**; SHA-256 de `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.
- Coincidencias exactas inequívocas: **529**.
- Aliases/excepciones explícitas: **13**.
- Revisiones manuales registradas: **86**.
- No encontrados tras aplicar aliases: **0**.
- Coincidencias exactas ambiguas: **0**.
- Códigos ICV duplicados, vacíos o sin asignar: **0**.
- Códigos con ceros iniciales: conservados como texto de cinco dígitos.

### Métodos

| Método | Filas | Regla |
|---|---:|---|
| `alias` | 13 | Código fijado en el fichero de aliases aprobado. |
| `exact_primary` | 457 | Igualdad literal inequívoca con `nom_mun`. |
| `exact_variant` | 72 | Igualdad literal inequívoca con otra variante ICV publicada. |

La normalización Unicode NFKC, de espacios, caja, apóstrofos y separadores `/` solo se usa para proponer candidatos al diagnosticar un nombre sin resolver. No se usa similitud aproximada ni se aprueba ninguna asignación normalizada automáticamente.

### Conteos por zona

| `idZonaPrevifoc` | Municipios |
|---:|---:|
| 53 | 28 |
| 54 | 64 |
| 55 | 40 |
| 56 | 113 |
| 57 | 61 |
| 58 | 190 |
| 59 | 46 |

## Aliases y excepciones aprobados

| Nombre 112CV | Código ICV | `nom_mun` | `noms_mun` | Motivo | Revisión |
|---|---|---|---|---|---|
| Alfarp | `46026` | Alfarb | Alfarb | El 112CV publica Alfarp y el ICV publica Alfarb en todas sus variantes; se fija la diferencia ortográfica final p/b. | approved (2026-07-18) |
| Algar de Palancia | `46028` | Algar de Palància | Algar de Palància | La única diferencia es el acento de Palància en la denominación ICV; no se elimina el acento automáticamente. | approved (2026-07-18) |
| Alqueries, les/Alquerías del Niño Perdido | `12901` | les Alqueries | les Alqueries/Alquerías del Niño Perdido | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Camp de Mirra, el/Campo de Mirra | `03051` | el Camp de Mirra | el Camp de Mirra/Campo de Mirra | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Fondó de les Neus, el/Hondón de las Nieves | `03077` | el Fondó de les Neus | el Fondó de les Neus/Hondón de las Nieves | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Novetlè/Novelé | `46180` | Novetlè | Novetlè | El 112CV publica una forma bilingüe y el ICV solo conserva Novetlè en sus variantes nominales. | approved (2026-07-18) |
| Orxa, l'/Lorcha | `03084` | l'Orxa | l'Orxa/Lorcha | El 112CV pospone el artículo apostrofado; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Pobla de Benifassà, la | `12093` | La Pobla de Benifassà | La Pobla de Benifassà | El 112CV pospone y escribe en minúscula el artículo; el ICV lo antepone como La. | approved (2026-07-18) |
| Poble Nou de Benitatxell, el/Benitachell | `03042` | el Poble Nou de Benitatxell | el Poble Nou de Benitatxell/Benitachell | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Torre d'en Besora, la | `12119` | la Torre d'En Besora | la Torre d'En Besora | El 112CV pospone el artículo y usa en minúscula; el ICV antepone la y capitaliza En. | approved (2026-07-18) |
| Torre de les Maçanes, la/Torremanzanas | `03132` | la Torre de les Maçanes | la Torre de les Maçanes/Torremanzanas | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Useres, les/Useras | `12122` | les Useres | les Useres/Useras | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |
| Vila Joiosa, la/Villajoyosa | `03139` | la Vila Joiosa | la Vila Joiosa/Villajoyosa | El 112CV pospone el artículo valenciano; el ICV lo antepone en la forma bilingüe. | approved (2026-07-18) |

## Casos de revisión manual

El registro versionado cubre todas las denominaciones bilingües, todos los artículos pospuestos detectados, todas las excepciones y las muestras mínimas Ademuz, València y Alacant/Alicante.

| Nombre 112CV | Código ICV | Categorías | `noms_mun` contrastado | Decisión |
|---|---|---|---|---|
| Ademuz | `46001` | `required_sample` | Ademuz | approved (2026-07-18) |
| Alacant/Alicante | `03014` | `required_sample;bilingual` | Alacant/Alicante | approved (2026-07-18) |
| Alboraia/Alboraya | `46013` | `bilingual` | Alboraia/Alboraya | approved (2026-07-18) |
| Alcoi/Alcoy | `03009` | `bilingual` | Alcoi/Alcoy | approved (2026-07-18) |
| Alcora, l' | `12005` | `postposed_article` | l'Alcora | approved (2026-07-18) |
| Alcúdia de Crespins, l' | `46020` | `postposed_article` | l'Alcúdia de Crespins | approved (2026-07-18) |
| Alcúdia, l' | `46019` | `postposed_article` | l'Alcúdia | approved (2026-07-18) |
| Alfarp | `46026` | `alias` | Alfarb | approved (2026-07-18) |
| Alfàs del Pi, l' | `03011` | `postposed_article` | l'Alfàs del Pi | approved (2026-07-18) |
| Algar de Palancia | `46028` | `alias` | Algar de Palància | approved (2026-07-18) |
| Alqueria d'Asnar, l' | `03017` | `postposed_article` | l'Alqueria d'Asnar | approved (2026-07-18) |
| Alqueria de la Comtessa, l' | `46037` | `postposed_article` | l'Alqueria de la Comtessa | approved (2026-07-18) |
| Alqueries, les/Alquerías del Niño Perdido | `12901` | `bilingual;postposed_article;alias` | les Alqueries/Alquerías del Niño Perdido | approved (2026-07-18) |
| Atzúbia, l' | `03001` | `postposed_article` | l'Atzúbia | approved (2026-07-18) |
| Benicàssim/Benicasim | `12028` | `bilingual` | Benicàssim/Benicasim | approved (2026-07-18) |
| Borriana/Burriana | `12032` | `bilingual` | Borriana/Burriana | approved (2026-07-18) |
| Camp de Mirra, el/Campo de Mirra | `03051` | `bilingual;postposed_article;alias` | el Camp de Mirra/Campo de Mirra | approved (2026-07-18) |
| Campello, el | `03050` | `postposed_article` | el Campello | approved (2026-07-18) |
| Castell de Guadalest, el | `03075` | `postposed_article` | el Castell de Guadalest | approved (2026-07-18) |
| Chilches/Xilxes | `12053` | `bilingual` | Chilches/Xilxes | approved (2026-07-18) |
| Coves de Vinromà, les | `12050` | `postposed_article` | les Coves de Vinromà | approved (2026-07-18) |
| Eliana, l' | `46116` | `postposed_article` | l'Eliana | approved (2026-07-18) |
| Elx/Elche | `03065` | `bilingual` | Elx/Elche | approved (2026-07-18) |
| Fondó de les Neus, el/Hondón de las Nieves | `03077` | `bilingual;postposed_article;alias` | el Fondó de les Neus/Hondón de las Nieves | approved (2026-07-18) |
| Font d'en Carròs, la | `46127` | `postposed_article` | la Font d'en Carròs | approved (2026-07-18) |
| Font de la Figuera, la | `46128` | `postposed_article` | la Font de la Figuera | approved (2026-07-18) |
| Genovés, el | `46132` | `postposed_article` | el Genovés | approved (2026-07-18) |
| Granja de la Costera, la | `46137` | `postposed_article` | la Granja de la Costera | approved (2026-07-18) |
| Jana, la | `12070` | `postposed_article` | la Jana | approved (2026-07-18) |
| Llosa de Ranes, la | `46157` | `postposed_article` | la Llosa de Ranes | approved (2026-07-18) |
| Llosa, la | `12074` | `postposed_article` | la Llosa | approved (2026-07-18) |
| Llucena/Lucena del Cid | `12072` | `bilingual` | Llucena/Lucena del Cid | approved (2026-07-18) |
| Mata de Morella, la | `12075` | `postposed_article` | la Mata de Morella | approved (2026-07-18) |
| Moixent/Mogente | `46170` | `bilingual` | Moixent/Mogente | approved (2026-07-18) |
| Montesinos, Los | `03903` | `postposed_article` | Los Montesinos | approved (2026-07-18) |
| Montitxelvo/Montichelvo | `46175` | `bilingual` | Montitxelvo/Montichelvo | approved (2026-07-18) |
| Montroi/Montroy | `46176` | `bilingual` | Montroi/Montroy | approved (2026-07-18) |
| Monòver/Monóvar | `03089` | `bilingual` | Monòver/Monóvar | approved (2026-07-18) |
| Novetlè/Novelé | `46180` | `bilingual;alias` | Novetlè | approved (2026-07-18) |
| Nucia, la | `03094` | `postposed_article` | la Nucia | approved (2026-07-18) |
| Nàquera/Náquera | `46178` | `bilingual` | Nàquera/Náquera | approved (2026-07-18) |
| Olleria, l' | `46183` | `postposed_article` | l'Olleria | approved (2026-07-18) |
| Orpesa/Oropesa del Mar | `12085` | `bilingual` | Orpesa/Oropesa del Mar | approved (2026-07-18) |
| Orxa, l'/Lorcha | `03084` | `bilingual;postposed_article;alias` | l'Orxa/Lorcha | approved (2026-07-18) |
| Palomar, el | `46189` | `postposed_article` | el Palomar | approved (2026-07-18) |
| Peníscola/Peñíscola | `12089` | `bilingual` | Peníscola/Peñíscola | approved (2026-07-18) |
| Pinós, el/Pinoso | `03105` | `bilingual;postposed_article` | Pinós, el/Pinoso | approved (2026-07-18) |
| Pobla de Benifassà, la | `12093` | `postposed_article;alias` | La Pobla de Benifassà | approved (2026-07-18) |
| Pobla de Farnals, la | `46199` | `postposed_article` | la Pobla de Farnals | approved (2026-07-18) |
| Pobla de Vallbona, la | `46202` | `postposed_article` | la Pobla de Vallbona | approved (2026-07-18) |
| Pobla del Duc, la | `46200` | `postposed_article` | la Pobla del Duc | approved (2026-07-18) |
| Pobla Llarga, la | `46203` | `postposed_article` | la Pobla Llarga | approved (2026-07-18) |
| Pobla Tornesa, la | `12094` | `postposed_article` | la Pobla Tornesa | approved (2026-07-18) |
| Poble Nou de Benitatxell, el/Benitachell | `03042` | `bilingual;postposed_article;alias` | el Poble Nou de Benitatxell/Benitachell | approved (2026-07-18) |
| Poblets, els | `03901` | `postposed_article` | els Poblets | approved (2026-07-18) |
| Puig de Santa Maria, el | `46204` | `postposed_article` | el Puig de Santa Maria | approved (2026-07-18) |
| Real de Gandia, el | `46211` | `postposed_article` | el Real de Gandia | approved (2026-07-18) |
| Romana, la | `03114` | `postposed_article` | la Romana | approved (2026-07-18) |
| Ràfol d'Almúnia, el | `03110` | `postposed_article` | el Ràfol d'Almúnia | approved (2026-07-18) |
| Sagunt/Sagunto | `46220` | `bilingual` | Sagunt/Sagunto | approved (2026-07-18) |
| Salzadella, la | `12098` | `postposed_article` | la Salzadella | approved (2026-07-18) |
| Sant Jordi/San Jorge | `12099` | `bilingual` | Sant Jordi/San Jorge | approved (2026-07-18) |
| Sant Vicent del Raspeig/San Vicente del Raspeig | `03122` | `bilingual` | Sant Vicent del Raspeig/San Vicente del Raspeig | approved (2026-07-18) |
| Serratella, la | `12103` | `postposed_article` | la Serratella | approved (2026-07-18) |
| Suera/Sueras | `12108` | `bilingual` | Suera/Sueras | approved (2026-07-18) |
| Toro, El | `12115` | `postposed_article` | El Toro | approved (2026-07-18) |
| Torre d'en Besora, la | `12119` | `postposed_article;alias` | la Torre d'En Besora | approved (2026-07-18) |
| Torre d'en Doménec, la | `12120` | `postposed_article` | la Torre d'en Doménec | approved (2026-07-18) |
| Torre de les Maçanes, la/Torremanzanas | `03132` | `bilingual;postposed_article;alias` | la Torre de les Maçanes/Torremanzanas | approved (2026-07-18) |
| Useres, les/Useras | `12122` | `bilingual;postposed_article;alias` | les Useres/Useras | approved (2026-07-18) |
| Vall d'Alcalà, la | `03134` | `postposed_article` | la Vall d'Alcalà | approved (2026-07-18) |
| Vall d'Ebo, la | `03135` | `postposed_article` | la Vall d'Ebo | approved (2026-07-18) |
| Vall d'Uixó, la | `12126` | `postposed_article` | la Vall d'Uixó | approved (2026-07-18) |
| Vall de Gallinera, la | `03136` | `postposed_article` | la Vall de Gallinera | approved (2026-07-18) |
| Vall de Laguar, la | `03137` | `postposed_article` | la Vall de Laguar | approved (2026-07-18) |
| València | `46250` | `required_sample` | València | approved (2026-07-18) |
| Verger, el | `03138` | `postposed_article` | el Verger | approved (2026-07-18) |
| Vila Joiosa, la/Villajoyosa | `03139` | `bilingual;postposed_article;alias` | la Vila Joiosa/Villajoyosa | approved (2026-07-18) |
| Vilafranca/Villafranca del Cid | `12129` | `bilingual` | Vilafranca/Villafranca del Cid | approved (2026-07-18) |
| Vilallonga/Villalonga | `46255` | `bilingual` | Vilallonga/Villalonga | approved (2026-07-18) |
| Vilavella, la | `12136` | `postposed_article` | la Vilavella | approved (2026-07-18) |
| Xixona/Jijona | `03083` | `bilingual` | Xixona/Jijona | approved (2026-07-18) |
| Xodos/Chodos | `12055` | `bilingual` | Xodos/Chodos | approved (2026-07-18) |
| Xàbia/Jávea | `03082` | `bilingual` | Xàbia/Jávea | approved (2026-07-18) |
| Yesa, La | `46262` | `postposed_article` | La Yesa | approved (2026-07-18) |
| Énova, l' | `46119` | `postposed_article` | l'Énova | approved (2026-07-18) |

## Diagnósticos finales

- No encontrados: ninguno.
- Duplicados de municipio 112CV: ninguno.
- Coincidencias exactas ambiguas: ninguna.
- Duplicados de `cod_ine_mun`: ninguno.
- Filas pendientes de revisión: ninguna.

## Condiciones para GEO-003

GEO-003 puede unir por `icv_cod_ine_mun` usando este `crosswalk.csv` y debe verificar su SHA-256. Debe mantener los códigos como texto. La confirmación formal de que PREVIFOC se define exactamente por municipios completos y la licencia específica 112CV continúan sin verificarse; no afectan a la cobertura del crosswalk local, pero deben mantenerse visibles antes de publicación.

No se han disuelto municipios, generado zonas, reproyectado, simplificado ni creado teselas en GEO-002.
