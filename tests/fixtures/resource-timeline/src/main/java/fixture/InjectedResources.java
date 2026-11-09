package fixture;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;

@Service
class ConstructorOperations {
    private final org.springframework.jdbc.core.JdbcOperations jdbc;
    @Autowired ConstructorOperations(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public void read() { jdbc.queryForObject("SELECT * FROM constructor_accounts", String.class); }
}

@Service
class UnknownThenJdbcOperations {
    private final org.springframework.jdbc.core.JdbcOperations jdbc;
    @Autowired UnknownThenJdbcOperations(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public void read() { unknownReceiver.run(); jdbc.queryForObject("SELECT * FROM constructor_accounts", String.class); }
}

@Service
class SetterOperations {
    private JdbcTemplate jdbc;
    @Autowired public void setJdbc(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public void read() { jdbc.queryForList("SELECT * FROM setter_accounts"); }
    public void aliasRead() { JdbcTemplate alias = jdbc; alias.queryForList("SELECT * FROM alias_accounts"); }
}

@Service
class ExplicitOperations {
    private final JdbcTemplate jdbc = new JdbcTemplate(null);
    public void read() { jdbc.queryForList("SELECT * FROM explicit_accounts"); }
}

@Service
class ExplicitOperationsInterface {
    private final org.springframework.jdbc.core.JdbcOperations jdbc = new JdbcTemplate();
    public void read() { jdbc.queryForList("SELECT * FROM explicit_interface_accounts"); }
}

@Service
class QualifiedConstructorOperations {
    private final org.springframework.jdbc.core.JdbcOperations jdbc;
    @Autowired QualifiedConstructorOperations(@Qualifier("primary") JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public void read() { jdbc.queryForList("SELECT * FROM qualified_accounts"); }
}

@Service
class OptionalFieldOperations {
    @Autowired(required = false) JdbcTemplate jdbc;
    public void read() { jdbc.queryForList("SELECT * FROM optional_accounts"); }
}

@Service
class PassedAliasOperations {
    @Autowired JdbcTemplate jdbc;
    public void dispatch() { write(jdbc); }
    private void write(JdbcTemplate passed) { passed.update("UPDATE passed_accounts SET value = 1"); }
}

@Service
class MultiBatchOperations {
    @Autowired JdbcTemplate jdbc;
    public void execute() {
        jdbc.batchUpdate("UPDATE first_resource SET value = 1", "UPDATE second_resource SET value = 2");
    }
}

@Service
class TransactionScenarioB {
    @Autowired JdbcTemplate jdbcB;
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void changeB() { jdbcB.update("UPDATE resource_b SET value = 1"); }
}

@Service
class TransactionScenarioA {
    @Autowired TransactionScenarioB serviceB;
    @Autowired JdbcTemplate jdbcA;
    @Transactional
    public void forward() { serviceB.changeB(); jdbcA.update("UPDATE resource_a SET value = 1"); }
    @Transactional
    public void reverse() { jdbcA.update("UPDATE resource_a SET value = 1"); serviceB.changeB(); }
}
