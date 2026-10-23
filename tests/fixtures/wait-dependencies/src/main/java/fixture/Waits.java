package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
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
class Paths {
    private final JdbcTemplate jdbc = new JdbcTemplate();
    @Autowired Inner inner;
    @Transactional public void xy() { jdbc.update("DELETE FROM X"); jdbc.update("DELETE FROM Y"); }
    @Transactional public void yx() { jdbc.update("DELETE FROM Y"); jdbc.update("DELETE FROM X"); }
    @Transactional public void outer() { jdbc.update("DELETE FROM X"); inner.fresh(); }
    @Transactional public void repeated() { inner.required(); inner.required(); }
    @Transactional public void required() { inner.required(); jdbc.update("DELETE FROM X"); }
    @Transactional public void nested() { inner.nested(); jdbc.update("DELETE FROM X"); }
    @Transactional public void frontier() { jdbc.update("DELETE FROM X"); unresolved.run(); jdbc.update("DELETE FROM Y"); }
    @Transactional public void unordered() { if (flag) { jdbc.update("DELETE FROM X"); } jdbc.update("DELETE FROM Y"); }
    @Transactional public void read() { jdbc.queryForList("SELECT * FROM X"); }
    @Transactional public void request() { jdbc.queryForList("SELECT * FROM X FOR UPDATE"); }
    @Transactional public void asyncCaller() { inner.async(); }
    @Transactional public void unknownSql() { jdbc.execute("SELECT a FROM X WHERE id = 1"); }
}
@Service
class Inner {
    private final JdbcTemplate jdbc = new JdbcTemplate();
    @Transactional(propagation = Propagation.REQUIRES_NEW) public void fresh() { jdbc.queryForList("SELECT * FROM X FOR UPDATE"); }
    @Transactional public void required() { jdbc.update("DELETE FROM X"); }
    @Transactional(propagation = Propagation.NESTED) public void nested() { jdbc.update("DELETE FROM X"); }
    @Async public void async() { jdbc.update("DELETE FROM X"); }
}
