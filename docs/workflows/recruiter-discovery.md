# Recruiter Discovery Workflow

## Goal

Identify legitimate, publicly available recruiting contacts for target companies without scraping private data.

## Flow

```mermaid
sequenceDiagram
    participant RDA as Recruiter Discovery Agent
    participant Source as Public Source Adapter
    participant Verify as Affiliation Verifier
    participant DB as Database

    RDA->>Source: search(company, role)
    Source-->>RDA: candidate contacts + source URLs
    RDA->>Verify: check_affiliation(contact, company)
    Verify-->>RDA: confidence_score
    alt confidence >= 70
        RDA->>DB: store as VERIFIED
    else
        RDA->>DB: store as GUESSED (not surfaced)
    end
```

## Permitted Sources

* Official company career / team pages.
* Public recruiting directories.
* Professional networking pages where data is voluntarily public.

## Prohibited

* Scraping private contact databases.
* Guessing email addresses.
* Harvesting contacts from closed groups.

## Outputs

* `RecruiterContact` with `contact_type` and `confidence_score`.
* Only `VERIFIED` contacts are shown to the user.
