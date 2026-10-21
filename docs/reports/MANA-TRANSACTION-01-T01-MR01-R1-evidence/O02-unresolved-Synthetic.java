// Synthetic supplied IR premises; not independently parsed or runtime verified.
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.*;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class Config {
  @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}
@Service
class Review {
  @Autowired Other other;
  public void plain() {}
  // F1
  @Transactional(transactionManager = "tx")
  public void outer() { System.gc(); other.inner(); }
}
@Service
class Other {
  @Autowired Other other;
  public void plain() {}
  // F2
  @Transactional(transactionManager = "tx")
  public void inner() { }
}
