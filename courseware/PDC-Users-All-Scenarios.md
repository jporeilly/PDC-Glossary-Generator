# PDC users — all four scenarios

One consolidated roster of every PDC account the workshops use,
generated from each scenario's `Workshop-00-Preflight/assets/users.csv`
(those files remain the per-scenario source of truth). Create the users
in PDC (Management -> Users & Communities) and set each password in
Keycloak (`pdc` realm, Temporary **off**) per Workshop 0.

Lab passwords are training values - change them in production. The
`catalog.admin` account carries **all seven roles** in the lab; if you
run several scenarios on one PDC instance, keep a single catalog.admin
and create only the eight named users per scenario.

## CSCU — Copper State Credit Union (lab password `copperstate`)

| Username | Email | PDC role(s) | Tier |
| --- | --- | --- | --- |
| elena.ramirez | elena.ramirez@copperstatecu.org | Data Steward; Business Steward | Expert |
| marcus.webb | marcus.webb@copperstatecu.org | Business Steward | Expert |
| nadia.flores | nadia.flores@copperstatecu.org | Business Steward | Expert |
| tom.callahan | tom.callahan@copperstatecu.org | Business Steward | Expert |
| omar.haddad | omar.haddad@copperstatecu.org | Data Storage Administrator | Expert |
| dana.ortiz | dana.ortiz@copperstatecu.org | Data Developer | Expert |
| jordan.blake | jordan.blake@copperstatecu.org | Data User | Business |
| riley.morgan | riley.morgan@copperstatecu.org | Business User | Business |
| catalog.admin | catalog.admin@copperstatecu.org | ALL SEVEN ROLES (lab) | Expert |

## RETAIL — Canyon Trail Outfitters (lab password `canyontrail`)

| Username | Email | PDC role(s) | Tier |
| --- | --- | --- | --- |
| sofia.marin | sofia.marin@canyontrailoutfitters.com | Data Steward; Business Steward | Expert |
| derek.boone | derek.boone@canyontrailoutfitters.com | Business Steward | Expert |
| ken.tanaka | ken.tanaka@canyontrailoutfitters.com | Business Steward | Expert |
| alicia.vega | alicia.vega@canyontrailoutfitters.com | Business Steward | Expert |
| leo.fischer | leo.fischer@canyontrailoutfitters.com | Data Storage Administrator | Expert |
| tessa.nguyen | tessa.nguyen@canyontrailoutfitters.com | Data Developer | Expert |
| casey.holt | casey.holt@canyontrailoutfitters.com | Data User | Business |
| robin.pierce | robin.pierce@canyontrailoutfitters.com | Business User | Business |
| catalog.admin | catalog.admin@canyontrailoutfitters.com | ALL SEVEN ROLES (lab) | Expert |

## HEALTH — Lakeshore Health Partners (lab password `lakeshore`)

| Username | Email | PDC role(s) | Tier |
| --- | --- | --- | --- |
| maya.lindqvist | maya.lindqvist@lakeshorehealth.org | Data Steward; Business Steward | Expert |
| anders.berg | anders.berg@lakeshorehealth.org | Business Steward | Expert |
| rosa.jimenez | rosa.jimenez@lakeshorehealth.org | Business Steward | Expert |
| hannah.weiss | hannah.weiss@lakeshorehealth.org | Business Steward | Expert |
| victor.osei | victor.osei@lakeshorehealth.org | Data Storage Administrator | Expert |
| ingrid.dahl | ingrid.dahl@lakeshorehealth.org | Data Developer | Expert |
| jamal.carter | jamal.carter@lakeshorehealth.org | Data User | Business |
| beth.nakamura | beth.nakamura@lakeshorehealth.org | Business User | Business |
| catalog.admin | catalog.admin@lakeshorehealth.org | ALL SEVEN ROLES (lab) | Expert |

## MFG — Cascade Precision Components (lab password `cascade`)

| Username | Email | PDC role(s) | Tier |
| --- | --- | --- | --- |
| nora.whitaker | nora.whitaker@cascadeprecision.com | Data Steward; Business Steward | Expert |
| felix.okonkwo | felix.okonkwo@cascadeprecision.com | Business Steward | Expert |
| yuki.mori | yuki.mori@cascadeprecision.com | Business Steward | Expert |
| silas.grant | silas.grant@cascadeprecision.com | Business Steward | Expert |
| petra.novak | petra.novak@cascadeprecision.com | Data Storage Administrator | Expert |
| andre.gibson | andre.gibson@cascadeprecision.com | Data Developer | Expert |
| mia.torres | mia.torres@cascadeprecision.com | Data User | Business |
| owen.fitch | owen.fitch@cascadeprecision.com | Business User | Business |
| catalog.admin | catalog.admin@cascadeprecision.com | ALL SEVEN ROLES (lab) | Expert |

*All scenario people are fictional and generated for training.*
