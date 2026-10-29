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
    @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}
@Service
class Calls {
    public void outsideRequired() { this.required(); }
    @Transactional public void activeRequired() { this.required(); }
    @Transactional public void activeNew() { this.independent(); }
    @Transactional public void activeNested() { this.nested(); }
    @Transactional public void following() { this.required(); this.plain(); }
    public void plain() {}
    @Transactional public void nonempty() { this.nonemptyRequired(); }
    @Transactional public final void nonemptyRequired() { this.plain(); }
    @Transactional public void asyncCaller() { this.asyncRequired(); }
    @org.springframework.scheduling.annotation.Async
    @Transactional public final void asyncRequired() {}
    @Transactional public void hazardCaller() { this.hazardRequired(); }
    @Transactional public final void hazardRequired() { Object ignored = null; }
    @Transactional public final void required() {}
    @Transactional(propagation = Propagation.REQUIRES_NEW) public final void independent() {}
    @Transactional(propagation = Propagation.NESTED) public final void nested() {}
}
