/// One driver in the 2026 F1 season roster.
#[derive(Debug, Clone, Copy)]
pub(crate) struct Driver {
    pub(crate) abbr: &'static str,
    pub(crate) name: &'static str,
    pub(crate) team: &'static str,
    /// Canonical lowercase last name used in prediction lists.
    /// Must match what `scoring::normalize` resolves to.
    pub(crate) key: &'static str,
}

/// Full 2026 F1 driver roster (22 drivers, 11 teams).
pub(crate) static ROSTER: &[Driver] = &[
    // McLaren
    Driver { abbr: "NOR", name: "Lando Norris",      team: "McLaren",      key: "norris" },
    Driver { abbr: "PIA", name: "Oscar Piastri",     team: "McLaren",      key: "piastri" },
    // Ferrari
    Driver { abbr: "LEC", name: "Charles Leclerc",   team: "Ferrari",      key: "leclerc" },
    Driver { abbr: "HAM", name: "Lewis Hamilton",    team: "Ferrari",      key: "hamilton" },
    // Mercedes
    Driver { abbr: "RUS", name: "George Russell",    team: "Mercedes",     key: "russell" },
    Driver { abbr: "ANT", name: "Kimi Antonelli",    team: "Mercedes",     key: "antonelli" },
    // Red Bull
    Driver { abbr: "VER", name: "Max Verstappen",    team: "Red Bull",     key: "verstappen" },
    Driver { abbr: "HAD", name: "Isack Hadjar",      team: "Red Bull",     key: "hadjar" },
    // Racing Bulls
    Driver { abbr: "LAW", name: "Liam Lawson",       team: "Racing Bulls", key: "lawson" },
    Driver { abbr: "LIN", name: "Arvid Lindblad",    team: "Racing Bulls", key: "lindblad" },
    // Aston Martin
    Driver { abbr: "ALO", name: "Fernando Alonso",   team: "Aston Martin", key: "alonso" },
    Driver { abbr: "STR", name: "Lance Stroll",      team: "Aston Martin", key: "stroll" },
    // Williams
    Driver { abbr: "SAI", name: "Carlos Sainz",      team: "Williams",     key: "sainz" },
    Driver { abbr: "ALB", name: "Alexander Albon",   team: "Williams",     key: "albon" },
    // Alpine
    Driver { abbr: "GAS", name: "Pierre Gasly",      team: "Alpine",       key: "gasly" },
    Driver { abbr: "COL", name: "Franco Colapinto",  team: "Alpine",       key: "colapinto" },
    // Haas
    Driver { abbr: "OCO", name: "Esteban Ocon",      team: "Haas",         key: "ocon" },
    Driver { abbr: "BEA", name: "Oliver Bearman",    team: "Haas",         key: "bearman" },
    // Audi
    Driver { abbr: "HUL", name: "Nico Hulkenberg",   team: "Audi",         key: "hulkenberg" },
    Driver { abbr: "BOR", name: "Gabriel Bortoleto", team: "Audi",         key: "bortoleto" },
    // Cadillac
    Driver { abbr: "PER", name: "Sergio Perez",      team: "Cadillac",     key: "perez" },
    Driver { abbr: "BOT", name: "Valtteri Bottas",   team: "Cadillac",     key: "bottas" },
];

/// Return the driver with the given canonical key (case-insensitive), or `None`.
pub(crate) fn by_key(key: &str) -> Option<&'static Driver> {
    let k = key.to_lowercase();
    ROSTER.iter().find(|d| d.key == k.as_str())
}
