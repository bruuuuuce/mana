package selftest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
@EnableTransactionManagement(mode = org.springframework.context.annotation.AdviceMode.ASPECTJ)
class Config {
    @Bean public DataSourceTransactionManager tx2() { return new DataSourceTransactionManager(); }
    @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}
@Service
class Calls {
    public void outsideRequired() { this.required(); }
    @Transactional(transactionManager = "tx") public void activeRequired() { this.required(); }
    @Transactional public void activeNew() { this.independent(); }
    @Transactional public void activeNested() { this.nested(); }
    @Transactional public final void required() {}
    @Transactional(propagation = Propagation.REQUIRES_NEW) public void independent() {}
    @Transactional(propagation = Propagation.NESTED) public void nested() {}
}
