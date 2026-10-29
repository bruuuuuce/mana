package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.scheduling.annotation.Async;

@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class Config {
    @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}
@Service
class A {
    @Autowired B b;
    @Transactional public void required() { b.required(); }
    @Transactional public void independent() { b.independent(); }
    @Transactional public void nested() { b.nested(); }
    public void outside() { b.required(); }
    @Transactional public void inherited() { b.plain(); }
    @Transactional public void self() { this.localNew(); }
    @Transactional(propagation = Propagation.REQUIRES_NEW) public void localNew() {}
    @Transactional public void unsupported() { b.supports(); }
    @Transactional public void ambiguous() { b.nested(); }
    @Transactional public void intermediate() { b.intermediate(); }
    @Transactional public void async() { b.async(); }
    @Transactional public void privateCall() { this.localPrivate(); }
    @Transactional(propagation = Propagation.REQUIRES_NEW) private void localPrivate() {}
    @Transactional public void conditional() { if (true) b.required(); }
    public void selfOutside() { this.localNew(); }
    @Transactional public void multiple() { b.required(); b.independent(); b.required(); }
    @Transactional public void reflective() throws Exception { Class.forName("fixture.B"); }
}
@Service
class B {
    @Autowired C c;
    @Transactional public void required() {}
    @Transactional(propagation = Propagation.REQUIRES_NEW) public void independent() {}
    @Transactional(propagation = Propagation.NESTED) public void nested() {}
    public void plain() {}
    public void intermediate() { c.required(); }
    @Async @Transactional public void async() {}
    @Transactional(propagation = Propagation.SUPPORTS) public void supports() {}
}
@Service
@Transactional
class C {
    public void required() {}
    @Transactional(propagation = Propagation.REQUIRES_NEW) public void override() {}
}
