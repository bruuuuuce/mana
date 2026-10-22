package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;

@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class Config {
    @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}
@Service
class Entry {
    @Autowired Operations operations;
    @Transactional public void required() { operations.required(); }
    @Transactional public void independent() { operations.independent(); }
    @Transactional public void nested() { operations.nested(); }
    public void outside() { operations.read(); }
    public void unknown() { operations.read(); }
    public void async() { operations.async(); }
    @Transactional public void ambiguousManager() { operations.read(); }
    @Transactional public void afterIndependent() { operations.emptyIndependent(); operations.write(); }
    @Transactional public void unresolved() { operations.unresolved(); operations.write(); }
}
@Service
class Operations {
    @Autowired JdbcTemplate jdbc;
    @Autowired @Qualifier("unresolvedJdbc") JdbcTemplate ambiguousJdbc;
    @Transactional public void required() { jdbc.update("UPDATE accounts SET balance = 1"); }
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void independent() { jdbc.update("UPDATE ledger SET amount = 2"); }
    @Transactional(propagation = Propagation.NESTED)
    public void nested() { jdbc.execute("SELECT * FROM accounts FOR UPDATE"); }
    public void read() { jdbc.queryForList("SELECT * FROM accounts"); }
    public void write() { jdbc.update("DELETE FROM accounts"); }
    public void dynamic() { jdbc.execute(sql()); }
    public String sql() { return "SELECT * FROM accounts"; }
    public void unsupportedSql() { jdbc.execute("SELECT a FROM accounts JOIN ledger ON accounts.id = ledger.id"); }
    public void unknownApi() { jdbc.call("SELECT * FROM accounts"); }
    public void ambiguousDatasource() { ambiguousJdbc.update("DELETE FROM accounts"); }
    public void sequence() { jdbc.execute("SELECT * FROM accounts"); jdbc.update("DELETE FROM ledger"); }
    public void commented() { /* jdbc.execute("DELETE FROM invented"); */ jdbc.execute("SELECT * FROM accounts"); }
    @Async public void async() { jdbc.update("DELETE FROM accounts"); }
    public void unresolved() { unknownReceiver.run(); }
    @Transactional(propagation = Propagation.REQUIRES_NEW) public void emptyIndependent() {}
}
