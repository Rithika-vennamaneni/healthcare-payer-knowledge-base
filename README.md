#  Healthcare Payer Knowledge Base


##  **System Architecture**

```
┌─────────────────────────────────────────────────────────┐
│                Healthcare Knowledge Base                │
├─────────────────────────────────────────────────────────┤
│   Web Crawler (Selenium)                            │
│     ├── Dynamic content handling                       │
│     ├── Multi-payer portal navigation                  │
│     └── Respectful crawling with rate limits           │
│                                                         │
│   PDF Processor (PyMuPDF + PyPDF2)                  │
│     ├── Dual extraction methods                        │
│     ├── Fallback processing                            │
│     └── Content validation                             │
│                                                         │
│   Rule Extraction Engine                            │
│     ├── Regex pattern matching                         │
│     ├── Content classification                         │
│     ├── Geographic zone detection                      │
│     └── JSON structure generation                      │
│                                                         │
│   Knowledge Base                                     │
│     ├── Structured JSON output                         │
│     ├── Queryable format                               │
│     └── API-ready data                                 │
└─────────────────────────────────────────────────────────┘
```

---


##  **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Healthcare Payer Knowledge Base - Automated Rule Extraction System**
