# Research Methodology: FBIHM Inventory Engine

This document outlines the systematic process followed during the development and research of the **FBIHM Inventory Engine**.

---

## 1. Research Design
The study employed an **Applied Research** design using the **Experimental Software Engineering** approach. The goal was to build a functional prototype that solves real-world inventory problems and measure its effectiveness.

## 2. Software Development Life Cycle (SDLC)
We utilized the **Agile Development Model**, specifically **Scrum**, which allowed for:
- **Sprints:** Developing individual modules (Auth, Inventory, POS, Reporting) in 2-week cycles.
- **Continuous Feedback:** Testing the UI with potential users early in the process.
- **Flexibility:** Migrating from SQLite to MongoDB Atlas and implementing strict ISO 8601 data standards when precision requirements became clear.

## 3. Data Collection Methods
- **Interviews:** Informal discussions with small business owners to identify "pain points" in their current manual systems.
- **Observation:** Watching the current checkout process in local stores to understand high-speed transaction needs.
- **System Logs:** Automatically generated logs with ISO 8601 timestamps used to identify common user errors and system crashes during the pilot phase.

## 4. Technical Stack Justification
- **Python (Flask):** Chosen for its rapid development and extensive library support for data processing (Pandas) and imaging (Pillow).
- **MongoDB Atlas:** Chosen to handle the "Unstructured" nature of retail items and provide cloud-native data persistence.
- **ISO 8601 Standardization:** Implemented to ensure global sortability and prevent date-parsing errors in business analytics.
- **SocketIO:** Chosen to fulfill the requirement for **Real-Time Visibility**, essential for preventing double-selling.

## 5. Development Phases
1.  **Requirement Analysis:** Defining core features (Stock tracking, POS, Reporting).
2.  **System Design:** Drafting the NoSQL schema and "Facebook-style" wireframes.
3.  **Implementation:** Coding the Flask backend and dynamic JavaScript frontend.
4.  **Branding Engine:** Integrating Pillow for dynamic logo and profile picture embedding in reports.
5.  **Integration & Testing:** Connecting modules and running stress tests on the database.
6.  **Deployment:** Setting up the Gitea CI/CD workflow and the 24/7 Watchdog daemon.

## 6. Verification & Validation
- **Functional Testing:** Ensuring every button and route performs its intended action.
- **Data Integrity Audit:** Verifying that all transactions follow the ISO 8601 standard.
- **Performance Testing:** Measuring response time of the POS checkout under simulated load.
- **User Validation:** A final walkthrough with a store manager to confirm that the system meets branded reporting needs.
